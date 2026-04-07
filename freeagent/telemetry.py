"""
Telemetry — built-in metrics, always on.

Embedded directly in the agent loop. No imports needed by the user.
Access via agent.metrics after any run.

    agent = Agent(model="qwen3:8b", tools=[my_tool])
    agent.run("What's the weather?")

    print(agent.metrics)                 # quick summary
    print(agent.metrics.last_run)        # last run details
    print(agent.metrics.tool_stats())    # per-tool breakdown
    agent.metrics.to_json("metrics.json") # export

Optional OpenTelemetry: install freeagent-sdk[otel] and set OTEL_EXPORTER_OTLP_ENDPOINT.
Traces and metrics flow automatically — no code changes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


# ── Records ───────────────────────────────────────────────

@dataclass
class ToolCallRecord:
    """A single tool invocation."""
    name: str
    args: dict
    success: bool = True
    duration_ms: float = 0
    result_preview: str = ""
    error: str = ""


@dataclass
class TraceEvent:
    """A single event in a run's trace timeline."""
    timestamp: float  # seconds since run start
    event_type: str
    data: dict = field(default_factory=dict)


@dataclass
class RunRecord:
    """A single agent.run() invocation."""
    run_id: int = 0
    model: str = ""
    mode: str = ""
    user_input: str = ""
    response: str = ""
    start_time: float = 0
    elapsed_ms: float = 0
    iterations: int = 0
    model_calls: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    validation_errors: int = 0
    retries: int = 0
    loop_detected: bool = False
    max_iter_hit: bool = False
    timed_out: bool = False
    fallback_model: str = ""
    trace_events: list[TraceEvent] = field(default_factory=list)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)

    @property
    def tools_used(self) -> list[str]:
        return [tc.name for tc in self.tool_calls]

    @property
    def error_count(self) -> int:
        return sum(1 for tc in self.tool_calls if not tc.success)

    def trace(self) -> str:
        """Human-readable trace timeline."""
        if not self.trace_events:
            return "No trace events recorded."
        lines = [f"Trace for run {self.run_id} ({self.model}, {self.mode}):"]
        for te in self.trace_events:
            ts = f"+{te.timestamp*1000:>7.0f}ms"
            detail = ""
            if te.event_type == "model_call_start":
                detail = f"iter={te.data.get('iteration', '?')}"
            elif te.event_type == "model_call_end":
                preview = te.data.get("content_preview", "")
                tc_count = len(te.data.get("tool_calls", []))
                if tc_count:
                    detail = f"tool_calls={tc_count}"
                elif preview:
                    detail = f'"{preview[:60]}"'
            elif te.event_type == "tool_call":
                detail = f"{te.data.get('name', '?')}({_fmt_args(te.data.get('args', {}))})"
            elif te.event_type == "tool_result":
                name = te.data.get("name", "?")
                ok = "ok" if te.data.get("success") else "FAIL"
                ms = te.data.get("duration_ms", 0)
                detail = f"{name} -> {ok} ({ms:.0f}ms)"
            elif te.event_type == "validation_error":
                detail = f"{te.data.get('tool_name', '?')}: {te.data.get('errors', [])}"
            elif te.event_type == "retry":
                detail = f"{te.data.get('tool_name', '?')} attempt #{te.data.get('count', '?')}"
            elif te.event_type == "loop_detected":
                detail = f"{te.data.get('tool_name', '?')}"
            elif te.event_type == "context_pruned":
                detail = f"dropped {te.data.get('messages_dropped', '?')} messages"
            else:
                detail = str(te.data) if te.data else ""
            lines.append(f"  {ts}  {te.event_type:<20s} {detail}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Markdown-formatted run report."""
        lines = [
            f"# Run {self.run_id}",
            "",
            f"- **Model:** {self.model} ({self.mode})",
            f"- **Input:** {self.user_input[:100]}",
            f"- **Elapsed:** {self.elapsed_ms:.0f}ms",
            f"- **Iterations:** {self.iterations}",
            f"- **Model calls:** {self.model_calls}",
            f"- **Tool calls:** {self.tool_call_count}",
        ]
        if self.validation_errors:
            lines.append(f"- **Validation errors:** {self.validation_errors}")
        if self.retries:
            lines.append(f"- **Retries:** {self.retries}")
        if self.loop_detected:
            lines.append("- **Loop detected**")
        if self.timed_out:
            lines.append("- **Timed out**")

        if self.tool_calls:
            lines.extend(["", "## Tool Calls", ""])
            for tc in self.tool_calls:
                status = "ok" if tc.success else f"FAIL: {tc.error}"
                lines.append(f"- `{tc.name}({_fmt_args(tc.args)})` -> {status} ({tc.duration_ms:.0f}ms)")

        if self.trace_events:
            lines.extend(["", "## Trace", "", "```"])
            lines.append(self.trace())
            lines.append("```")

        if self.response:
            lines.extend(["", "## Response", "", self.response[:500]])

        return "\n".join(lines)

    def summary(self) -> str:
        """One-line summary of the run."""
        tools = f", {self.tool_call_count} tools" if self.tool_call_count else ""
        flags = []
        if self.loop_detected:
            flags.append("LOOP")
        if self.timed_out:
            flags.append("TIMEOUT")
        if self.validation_errors:
            flags.append(f"{self.validation_errors}err")
        extra = f" [{','.join(flags)}]" if flags else ""
        return (
            f"Run {self.run_id}: {self.model} ({self.mode}) "
            f"{self.elapsed_ms:.0f}ms, {self.iterations} iters{tools}{extra}"
        )


def _fmt_args(args: dict) -> str:
    """Format args dict concisely for trace output."""
    if not args:
        return ""
    parts = [f"{k}={repr(v)}" for k, v in args.items()]
    result = ", ".join(parts)
    return result[:80] + "..." if len(result) > 80 else result


# ── Metrics (lives on agent.metrics) ──────────────────────

class Metrics:
    """
    Agent telemetry collector. Always active — zero config.

    Created automatically by Agent.__init__. Records every run,
    model call, tool call, validation error, retry, and circuit
    breaker event. Optionally bridges to OpenTelemetry.
    """

    def __init__(self):
        self.runs: list[RunRecord] = []
        self._run_counter: int = 0

        # Current run state (set during agent loop)
        self._current: RunRecord | None = None
        self._tool_timers: dict[str, float] = {}

        # OTEL bridge (lazy, optional)
        self._otel: _OtelBridge | None = _try_init_otel()

    # ── Called by the agent loop ─────────────────────────

    def start_run(self, user_input: str, model: str, mode: str):
        """Called at the start of agent.arun()."""
        self._run_counter += 1
        self._run_start_mono = time.monotonic()
        self._current = RunRecord(
            run_id=self._run_counter,
            model=model,
            mode=mode,
            user_input=user_input,
            start_time=time.time(),
        )
        self.runs.append(self._current)

        if self._otel:
            self._otel.start_run_span(user_input, model, mode)

    def end_run(self, response: str, elapsed_ms: float):
        """Called at the end of agent.arun()."""
        if self._current:
            self._current.response = response[:500] if response else ""
            self._current.elapsed_ms = elapsed_ms

        if self._otel:
            self._otel.end_run_span(
                elapsed_ms=elapsed_ms,
                iterations=self._current.iterations if self._current else 0,
                tool_calls=self._current.tool_call_count if self._current else 0,
            )

        self._current = None

    def _trace(self, event_type: str, data: dict | None = None):
        """Append a trace event to the current run."""
        if self._current:
            elapsed = time.monotonic() - self._run_start_mono
            self._current.trace_events.append(
                TraceEvent(timestamp=elapsed, event_type=event_type, data=data or {})
            )

    def record_model_call(self, iteration: int):
        """Called each time the model is invoked."""
        if self._current:
            self._current.model_calls += 1
            self._current.iterations = iteration + 1
        self._trace("model_call_start", {"iteration": iteration})

    def start_tool(self, tool_name: str, args: dict):
        """Called before tool execution."""
        self._tool_timers[tool_name] = time.monotonic()
        self._trace("tool_call", {"name": tool_name, "args": args})
        if self._otel:
            self._otel.start_tool_span(tool_name, args)

    def end_tool(self, tool_name: str, args: dict, success: bool,
                 result_preview: str = "", error: str = ""):
        """Called after tool execution."""
        duration = 0.0
        if tool_name in self._tool_timers:
            duration = (time.monotonic() - self._tool_timers.pop(tool_name)) * 1000

        record = ToolCallRecord(
            name=tool_name,
            args=dict(args) if args else {},
            success=success,
            duration_ms=duration,
            result_preview=result_preview,
            error=error,
        )

        if self._current:
            self._current.tool_calls.append(record)

        self._trace("tool_result", {
            "name": tool_name, "success": success,
            "duration_ms": duration, "preview": result_preview[:100],
        })

        if self._otel:
            self._otel.end_tool_span(tool_name, success, duration)

    def record_validation_error(self, tool_name: str):
        """Called on tool call validation failure."""
        if self._current:
            self._current.validation_errors += 1
        self._trace("validation_error", {"tool_name": tool_name})
        if self._otel:
            self._otel.record_event("validation_error", {"tool": tool_name})

    def record_retry(self, tool_name: str, retry_count: int):
        """Called on retry after validation failure."""
        if self._current:
            self._current.retries += 1
        self._trace("retry", {"tool_name": tool_name, "count": retry_count})
        if self._otel:
            self._otel.record_event("retry", {"tool": tool_name, "count": str(retry_count)})

    def record_loop_detected(self, tool_name: str):
        """Called when circuit breaker detects a loop."""
        if self._current:
            self._current.loop_detected = True
        self._trace("loop_detected", {"tool_name": tool_name})
        if self._otel:
            self._otel.record_event("loop_detected", {"tool": tool_name})

    def record_max_iterations(self, iteration: int):
        """Called when max iterations reached."""
        if self._current:
            self._current.max_iter_hit = True
        self._trace("max_iterations", {"iteration": iteration})
        if self._otel:
            self._otel.record_event("max_iterations", {"iteration": str(iteration)})

    def record_timeout(self):
        """Called on timeout."""
        if self._current:
            self._current.timed_out = True
        self._trace("timeout")
        if self._otel:
            self._otel.record_event("timeout", {})

    # ── Query ───────────────────────────────────────────

    @property
    def last_run(self) -> RunRecord | None:
        """Most recent run record."""
        return self.runs[-1] if self.runs else None

    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def total_tool_calls(self) -> int:
        return sum(r.tool_call_count for r in self.runs)

    @property
    def total_model_calls(self) -> int:
        return sum(r.model_calls for r in self.runs)

    @property
    def avg_latency_ms(self) -> float:
        if not self.runs:
            return 0
        return sum(r.elapsed_ms for r in self.runs) / len(self.runs)

    @property
    def avg_iterations(self) -> float:
        if not self.runs:
            return 0
        return sum(r.iterations for r in self.runs) / len(self.runs)

    def tool_stats(self) -> dict[str, dict]:
        """Per-tool breakdown: count, avg duration, error rate."""
        stats: dict[str, list] = {}
        for run in self.runs:
            for tc in run.tool_calls:
                stats.setdefault(tc.name, []).append(tc)

        result = {}
        for name, calls in stats.items():
            count = len(calls)
            errors = sum(1 for c in calls if not c.success)
            total_ms = sum(c.duration_ms for c in calls)
            result[name] = {
                "count": count,
                "avg_ms": round(total_ms / count, 1) if count else 0,
                "errors": errors,
                "error_rate": round(errors / count, 3) if count else 0,
            }
        return result

    # ── Export ──────────────────────────────────────────

    def to_dict(self) -> dict:
        """Full metrics export as a plain dict."""
        return {
            "total_runs": self.total_runs,
            "total_model_calls": self.total_model_calls,
            "total_tool_calls": self.total_tool_calls,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_iterations": round(self.avg_iterations, 1),
            "tool_stats": self.tool_stats(),
            "runs": [self._export_run(r) for r in self.runs],
        }

    def _export_run(self, r: RunRecord) -> dict:
        return {
            "run_id": r.run_id,
            "model": r.model,
            "mode": r.mode,
            "user_input": r.user_input[:100],
            "elapsed_ms": round(r.elapsed_ms, 1),
            "iterations": r.iterations,
            "model_calls": r.model_calls,
            "tool_calls": [
                {"name": tc.name, "success": tc.success,
                 "duration_ms": round(tc.duration_ms, 1)}
                for tc in r.tool_calls
            ],
            "validation_errors": r.validation_errors,
            "retries": r.retries,
            "loop_detected": r.loop_detected,
            "max_iter_hit": r.max_iter_hit,
            "timed_out": r.timed_out,
        }

    def to_json(self, path: str | None = None) -> str:
        """Export as JSON. Optionally write to file."""
        data = json.dumps(self.to_dict(), indent=2)
        if path:
            with open(path, "w") as f:
                f.write(data)
        return data

    def reset(self):
        """Clear all collected metrics."""
        self.runs.clear()
        self._current = None
        self._tool_timers.clear()
        self._run_counter = 0

    def __repr__(self) -> str:
        if not self.runs:
            return "Metrics(no runs yet)"
        last = self.runs[-1]
        return (
            f"Metrics(runs={self.total_runs}, "
            f"last: {last.elapsed_ms:.0f}ms, "
            f"{last.iterations} iters, "
            f"{last.tool_call_count} tools)"
        )

    def __str__(self) -> str:
        if not self.runs:
            return "No runs recorded."

        lines = [
            f"Runs: {self.total_runs}  |  "
            f"Model calls: {self.total_model_calls}  |  "
            f"Tool calls: {self.total_tool_calls}  |  "
            f"Avg latency: {self.avg_latency_ms:.0f}ms"
        ]

        ts = self.tool_stats()
        if ts:
            parts = []
            for name, s in ts.items():
                err = f" ({s['error_rate']:.0%} err)" if s["errors"] else ""
                parts.append(f"{name}: {s['count']}x avg {s['avg_ms']}ms{err}")
            lines.append("Tools: " + ", ".join(parts))

        for r in self.runs:
            flags = []
            if r.loop_detected:
                flags.append("LOOP")
            if r.max_iter_hit:
                flags.append("MAX_ITER")
            if r.timed_out:
                flags.append("TIMEOUT")
            if r.validation_errors:
                flags.append(f"{r.validation_errors} val_err")
            if r.retries:
                flags.append(f"{r.retries} retries")
            extra = f" [{', '.join(flags)}]" if flags else ""
            tools = ", ".join(r.tools_used) if r.tools_used else "none"
            lines.append(
                f"  Run {r.run_id}: {r.model} ({r.mode}) "
                f"{r.elapsed_ms:.0f}ms | {r.iterations} iters | "
                f"tools: [{tools}]{extra}"
            )

        return "\n".join(lines)


# ── OpenTelemetry Bridge (optional) ──────────────────────

class _OtelBridge:
    """OTEL tracer + meter. Only created if opentelemetry is installed."""

    def __init__(self):
        from opentelemetry import trace, metrics

        self._tracer = trace.get_tracer("freeagent-sdk")
        self._meter = metrics.get_meter("freeagent-sdk")

        self._run_duration = self._meter.create_histogram(
            "freeagent.run.duration_ms",
            description="Agent run duration in milliseconds",
        )
        self._run_iterations = self._meter.create_histogram(
            "freeagent.run.iterations",
            description="Agent loop iterations per run",
        )
        self._tool_duration = self._meter.create_histogram(
            "freeagent.tool.duration_ms",
            description="Tool call duration in milliseconds",
        )
        self._tool_counter = self._meter.create_counter(
            "freeagent.tool.calls",
            description="Total tool calls",
        )
        self._error_counter = self._meter.create_counter(
            "freeagent.errors",
            description="Errors by type",
        )

        self._spans: dict[str, Any] = {}

    def start_run_span(self, user_input: str, model: str, mode: str):
        span = self._tracer.start_span("agent.run")
        span.set_attribute("freeagent.model", model)
        span.set_attribute("freeagent.mode", mode)
        span.set_attribute("freeagent.user_input", user_input[:200])
        self._spans["run"] = span

    def end_run_span(self, elapsed_ms: float, iterations: int, tool_calls: int):
        span = self._spans.pop("run", None)
        if span:
            span.set_attribute("freeagent.elapsed_ms", elapsed_ms)
            span.set_attribute("freeagent.iterations", iterations)
            span.set_attribute("freeagent.tool_calls", tool_calls)
            span.end()
        self._run_duration.record(elapsed_ms)
        self._run_iterations.record(iterations)

    def start_tool_span(self, tool_name: str, args: dict):
        span = self._tracer.start_span(f"tool.{tool_name}")
        span.set_attribute("freeagent.tool.name", tool_name)
        self._spans[f"tool:{tool_name}"] = span

    def end_tool_span(self, tool_name: str, success: bool, duration_ms: float):
        key = f"tool:{tool_name}"
        span = self._spans.pop(key, None)
        if span:
            span.set_attribute("freeagent.tool.success", success)
            span.set_attribute("freeagent.tool.duration_ms", duration_ms)
            span.end()
        self._tool_duration.record(duration_ms, {"tool": tool_name})
        self._tool_counter.add(1, {"tool": tool_name, "success": str(success)})

    def record_event(self, name: str, attrs: dict):
        self._error_counter.add(1, {"type": name, **attrs})
        span = self._spans.get("run")
        if span:
            span.add_event(name, attributes=attrs)


def _try_init_otel() -> _OtelBridge | None:
    """Try to init OTEL. Returns None silently if not installed."""
    try:
        import opentelemetry  # noqa: F401
        return _OtelBridge()
    except ImportError:
        return None
