"""
The Agent — core of FreeAgent SDK.

Framework-assisted, not model-driven. The model does what it can.
The framework catches everything else.

Telemetry is built in — agent.metrics is always available.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from .config import AgentConfig
from .circuit_breaker import CircuitBreaker, BreakerAction
from .engines import NativeEngine, ReactEngine, EngineResult
from .hooks import HookRegistry, HookContext, HookEvent
from .memory import Memory, make_memory_tools
from .messages import Message
from .providers.ollama import OllamaProvider
from .skills import load_skills, build_skill_context, BUNDLED_SKILLS_DIR
from .telemetry import Metrics
from .tool import Tool
from .validator import Validator, ValidationOk, ValidationError


class Agent:
    """
    A local-first AI agent with guardrails, built-in telemetry, and memory.

    Usage:
        # Basic
        agent = Agent(model="qwen3:8b", tools=[my_tool])

        # With skills
        agent = Agent(
            model="qwen3:8b",
            tools=[weather, calculator],
            skills=["./my-skills"],   # directory of skill folders
        )

        response = agent.run("What's the weather?")
        print(agent.metrics)
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        system_prompt: str = "You are a helpful assistant.",
        tools: list[Tool] = None,
        config: AgentConfig = None,
        provider=None,
        skills: list = None,
        **kwargs,
    ):
        self.config = config or AgentConfig()
        self.config.model = model
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)

        self.system_prompt = system_prompt

        # Memory — markdown-backed, always on
        self.memory = Memory(memory_dir=kwargs.pop("memory_dir", None))

        # Memory tools — agent can read/write/search/list memory files
        memory_tools = make_memory_tools(self.memory)
        self.tools = (tools or []) + memory_tools

        # Skills — bundled skills always load, user skills extend them
        skill_sources = [BUNDLED_SKILLS_DIR]
        if skills:
            skill_sources.extend(skills)
        self.skills = load_skills(skill_sources)

        # Provider — use custom if given, otherwise default to Ollama
        if provider is not None:
            self.provider = provider
        else:
            self.provider = OllamaProvider(
                model=model,
                base_url=self.config.ollama_base_url,
            )

        # Engine selection
        if self.tools and self.config.supports_native_tools(model):
            self.engine = NativeEngine(self.provider)
            self._mode = "native"
        elif self.tools:
            self.engine = ReactEngine(self.provider)
            self._mode = "react"
        else:
            self.engine = None
            self._mode = "chat"

        # Guardrails
        self.validator = Validator(self.tools)
        self.breaker = CircuitBreaker(self.config)

        # Hooks
        self._hooks = HookRegistry()

        # Telemetry — always on, no setup needed
        self.metrics = Metrics()

    # ── Hook registration ────────────────────────────────

    def on(self, event: str | HookEvent, callback: Callable = None):
        """
        Register a hook. Works as decorator or direct call.

        @agent.on("before_tool")
        def my_hook(ctx):
            print(ctx.tool_name)

        # or
        agent.on("before_tool", my_callback)
        """
        if callback is not None:
            self._hooks.register(event, callback)
            return callback

        def decorator(fn):
            self._hooks.register(event, fn)
            return fn
        return decorator

    def off(self, event: str | HookEvent, callback: Callable):
        """Unregister a hook."""
        self._hooks.unregister(event, callback)

    def _fire(self, event: HookEvent, **kwargs) -> HookContext:
        """Fire a hook event and return the context."""
        ctx = HookContext(event=event, agent=self, **kwargs)
        return self._hooks.dispatch(ctx)

    # ── Run ──────────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """Run the agent synchronously."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return loop.run_in_executor(
                    pool, lambda: asyncio.run(self.arun(user_input))
                )
        except RuntimeError:
            return asyncio.run(self.arun(user_input))

    async def arun(self, user_input: str) -> str:
        """Run the agent asynchronously."""
        start = time.monotonic()
        self.breaker.reset()

        # ── Telemetry: start run
        self.metrics.start_run(user_input, self.config.model, self._mode)

        # Fire before_run hook
        ctx = self._fire(HookEvent.BEFORE_RUN, user_input=user_input)
        if ctx.override_response is not None:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.end_run(ctx.override_response, elapsed)
            return ctx.override_response

        # Build messages with skills + memory context
        system = self.system_prompt

        # Inject skills
        skill_context = build_skill_context(self.skills)
        if skill_context:
            system = f"{system}\n\n{skill_context}"

        # Inject memory
        mem_context = self.memory.to_system_prompt()
        if mem_context:
            system = f"{system}\n\n{mem_context}"

        messages = [
            Message.system(system),
            Message.user(user_input),
        ]

        # Simple chat (no tools)
        if not self.tools or self.engine is None:
            self.metrics.record_model_call(0)
            response = await self.provider.chat(
                messages, temperature=self.config.temperature
            )
            result = response.content
        else:
            # Agent loop with timeout
            try:
                result = await asyncio.wait_for(
                    self._agent_loop(messages),
                    timeout=self.config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                self.metrics.record_timeout()
                self._fire(HookEvent.ON_TIMEOUT, user_input=user_input)
                result = self._graceful_timeout(messages)

        elapsed = (time.monotonic() - start) * 1000

        # ── Telemetry: end run
        self.metrics.end_run(result, elapsed)

        # Fire after_run hook
        ctx = self._fire(
            HookEvent.AFTER_RUN,
            user_input=user_input,
            response=result,
            elapsed_ms=elapsed,
        )
        if ctx.override_response is not None:
            result = ctx.override_response

        return result

    async def _agent_loop(self, messages: list[Message]) -> str:
        """The core reason → act → observe loop."""
        retries_remaining = self.config.max_retries

        for iteration in range(self.config.max_iterations):
            # Fire before_model hook
            self._fire(HookEvent.BEFORE_MODEL, messages=messages, iteration=iteration)

            # ── Telemetry: model call
            self.metrics.record_model_call(iteration)

            # Get next action from engine
            result = await self.engine.execute(
                messages=messages,
                tools=self.tools,
                temperature=self.config.temperature,
            )

            # Fire after_model hook
            self._fire(
                HookEvent.AFTER_MODEL,
                model_response=result.content if not result.is_tool_call else result.tool_name,
                iteration=iteration,
            )

            # ── Text response (final answer) ──
            if not result.is_tool_call:
                messages.append(Message.assistant(result.content))
                return result.content

            # ── Tool call ──
            # Validate
            validation = self.validator.validate(
                result.tool_name, result.tool_args
            )

            if isinstance(validation, ValidationError):
                # ── Telemetry: validation error
                self.metrics.record_validation_error(result.tool_name)

                self._fire(
                    HookEvent.ON_VALIDATION_ERROR,
                    tool_name=result.tool_name,
                    args=result.tool_args,
                    errors=validation.errors,
                    schema=validation.schema,
                    retry_count=self.config.max_retries - retries_remaining,
                )

                messages.append(Message.tool_error(
                    result.tool_name,
                    validation.errors,
                    validation.schema,
                ))
                retries_remaining -= 1

                if retries_remaining <= 0:
                    messages.append(Message.system(
                        "Tool calls keep failing. Please provide your "
                        "best answer based on what you know."
                    ))

                # ── Telemetry: retry
                self.metrics.record_retry(
                    result.tool_name,
                    self.config.max_retries - retries_remaining,
                )

                self._fire(
                    HookEvent.ON_RETRY,
                    tool_name=result.tool_name,
                    retry_count=self.config.max_retries - retries_remaining,
                )
                continue

            # Circuit breaker
            breaker_result = self.breaker.check(
                result.tool_name, result.tool_args
            )

            if breaker_result.action == BreakerAction.LOOP_DETECTED:
                # ── Telemetry: loop
                self.metrics.record_loop_detected(result.tool_name)

                self._fire(
                    HookEvent.ON_LOOP,
                    tool_name=result.tool_name,
                    args=result.tool_args,
                )
                messages.append(Message.system(
                    f"STOP. {breaker_result.reason} "
                    "Give your best answer with the information gathered so far."
                ))
                continue

            if breaker_result.action == BreakerAction.MAX_ITERATIONS:
                # ── Telemetry: max iter
                self.metrics.record_max_iterations(iteration)

                self._fire(HookEvent.ON_MAX_ITER, iteration=iteration)
                return self._partial_answer(messages)

            # Fire before_tool hook
            tool = validation.tool
            ctx = self._fire(
                HookEvent.BEFORE_TOOL,
                tool_name=result.tool_name,
                args=validation.args,
                iteration=iteration,
            )

            # Hook can skip tool execution
            if ctx.skip:
                continue

            # ── Telemetry: start tool
            self.metrics.start_tool(result.tool_name, validation.args)

            # Execute the tool
            try:
                tool_result = await tool.execute(**validation.args)
            except Exception as e:
                self._fire(
                    HookEvent.ON_ERROR,
                    tool_name=result.tool_name,
                    error=e,
                )
                from .tool import ToolResult
                tool_result = ToolResult.fail(str(e))

            # ── Telemetry: end tool
            self.metrics.end_tool(
                tool_name=result.tool_name,
                args=validation.args,
                success=tool_result.success,
                result_preview=tool_result.to_message()[:100],
                error=tool_result.error or "",
            )

            # Fire after_tool hook
            self._fire(
                HookEvent.AFTER_TOOL,
                tool_name=result.tool_name,
                args=validation.args,
                result=tool_result,
                iteration=iteration,
            )

            # Add messages
            messages.append(Message.assistant(
                f"Calling {result.tool_name}...",
                tool_calls=[{
                    "function": {
                        "name": result.tool_name,
                        "arguments": result.tool_args,
                    }
                }],
            ))
            messages.append(Message.tool_result(
                result.tool_name,
                tool_result.to_message(),
            ))

            retries_remaining = self.config.max_retries

        return self._partial_answer(messages)

    # ── Graceful degradation ─────────────────────────────

    def _partial_answer(self, messages: list[Message]) -> str:
        tool_results = [
            m.content for m in messages
            if m.role == "tool" and m.content and "error" not in m.content.lower()
        ]
        if tool_results:
            return (
                "[Agent reached iteration limit. Partial results:]\n"
                + "\n".join(tool_results)
            )
        return "[Agent could not complete the task. Try a simpler query.]"

    def _graceful_timeout(self, messages: list[Message]) -> str:
        tool_results = [
            m.content for m in messages
            if m.role == "tool" and m.content and "error" not in m.content.lower()
        ]
        if tool_results:
            return (
                "[Timed out — partial data gathered:]\n"
                + "\n".join(tool_results)
            )
        return "[Request timed out. Try a simpler query or increase timeout.]"

    def __repr__(self) -> str:
        mem = f", memory={len(self.memory)}" if len(self.memory) > 0 else ""
        return (
            f"Agent(model='{self.config.model}', "
            f"mode='{self._mode}', "
            f"tools={[t.name for t in self.tools]}{mem})"
        )
