"""Tests for the trace inspection API."""

import pytest
from unittest.mock import patch

from freeagent import Agent
from freeagent.telemetry import Metrics, RunRecord, TraceEvent, ToolCallRecord
from freeagent.providers import ProviderResponse


# ── TraceEvent tests ──────────────────────────────────────

def test_trace_event_creation():
    te = TraceEvent(timestamp=0.5, event_type="tool_call", data={"name": "calc"})
    assert te.timestamp == 0.5
    assert te.event_type == "tool_call"
    assert te.data["name"] == "calc"


def test_trace_event_default_data():
    te = TraceEvent(timestamp=0.0, event_type="timeout")
    assert te.data == {}


# ── RunRecord trace methods ───────────────────────────────

def test_run_record_trace_empty():
    r = RunRecord(run_id=1, model="test", mode="chat")
    assert "No trace events" in r.trace()


def test_run_record_trace_with_events():
    r = RunRecord(run_id=1, model="test", mode="native")
    r.trace_events = [
        TraceEvent(0.0, "model_call_start", {"iteration": 0}),
        TraceEvent(0.5, "tool_call", {"name": "calc", "args": {"x": 1}}),
        TraceEvent(0.6, "tool_result", {"name": "calc", "success": True, "duration_ms": 100}),
        TraceEvent(1.0, "model_call_start", {"iteration": 1}),
    ]
    trace = r.trace()
    assert "Trace for run 1" in trace
    assert "model_call_start" in trace
    assert "tool_call" in trace
    assert "calc" in trace


def test_run_record_summary():
    r = RunRecord(run_id=1, model="qwen3:8b", mode="native", elapsed_ms=500, iterations=2)
    r.tool_calls = [ToolCallRecord(name="calc", args={"x": 1})]
    s = r.summary()
    assert "qwen3:8b" in s
    assert "500ms" in s
    assert "1 tools" in s


def test_run_record_summary_with_flags():
    r = RunRecord(run_id=1, model="test", mode="native", elapsed_ms=100, iterations=1,
                  loop_detected=True, validation_errors=2)
    s = r.summary()
    assert "LOOP" in s
    assert "2err" in s


def test_run_record_to_markdown():
    r = RunRecord(run_id=1, model="qwen3:8b", mode="native",
                  user_input="test query", response="test response",
                  elapsed_ms=500, iterations=2, model_calls=2)
    r.tool_calls = [ToolCallRecord(name="calc", args={"x": 1}, success=True, duration_ms=50)]
    r.trace_events = [TraceEvent(0.0, "model_call_start", {"iteration": 0})]
    md = r.to_markdown()
    assert "# Run 1" in md
    assert "qwen3:8b" in md
    assert "## Tool Calls" in md
    assert "calc" in md
    assert "## Trace" in md
    assert "## Response" in md


# ── Metrics trace recording ──────────────────────────────

def test_metrics_records_trace_events():
    m = Metrics()
    m.start_run("hello", "test", "chat")
    m.record_model_call(0)
    m.start_tool("calc", {"x": 1})
    m.end_tool("calc", {"x": 1}, success=True, result_preview="42")
    m.record_validation_error("bad_tool")
    m.record_retry("bad_tool", 1)
    m.end_run("done", 100.0)

    run = m.runs[0]
    assert len(run.trace_events) >= 4

    types = [te.event_type for te in run.trace_events]
    assert "model_call_start" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "validation_error" in types
    assert "retry" in types

    # Timestamps should be non-negative and increasing
    for te in run.trace_events:
        assert te.timestamp >= 0


def test_metrics_trace_loop_and_timeout():
    m = Metrics()
    m.start_run("hello", "test", "chat")
    m.record_loop_detected("calc")
    m.record_timeout()
    m.end_run("partial", 50.0)

    types = [te.event_type for te in m.runs[0].trace_events]
    assert "loop_detected" in types
    assert "timeout" in types


# ── Agent convenience methods ─────────────────────────────

class MockProvider:
    model = "test"
    async def chat(self, messages, temperature=0.1):
        return ProviderResponse(content="hello")
    async def chat_with_tools(self, messages, tools, temperature=0.1):
        return ProviderResponse(content="hello")
    async def chat_with_format(self, messages, schema, temperature=0.1):
        return "{}"
    async def chat_stream(self, messages, temperature=0.1):
        from freeagent.providers import StreamChunk
        yield StreamChunk(content="hello", done=True)
    async def chat_stream_with_tools(self, messages, tools, temperature=0.1):
        from freeagent.providers import StreamChunk
        yield StreamChunk(content="hello", done=True)


def test_agent_last_run_none():
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(model="test", provider=MockProvider(), tools=[],
                      conversation=None, auto_tune=False)
    assert agent.last_run is None


def test_agent_trace_no_runs():
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(model="test", provider=MockProvider(), tools=[],
                      conversation=None, auto_tune=False)
    assert agent.trace() == "No runs yet."


def test_agent_trace_after_run():
    with patch("freeagent.agent.make_memory_tools", return_value=[]):
        agent = Agent(model="test", provider=MockProvider(), tools=[],
                      conversation=None, auto_tune=False)
    agent.run("hello")
    assert agent.last_run is not None
    assert agent.last_run.model == "test"
    trace = agent.trace()
    # Should have at least model_call_start event
    assert "model_call_start" in trace
