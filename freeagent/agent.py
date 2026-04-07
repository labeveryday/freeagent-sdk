"""
The Agent — core of FreeAgent SDK.

Framework-assisted, not model-driven. The model does what it can.
The framework catches everything else.

Telemetry is built in — agent.metrics is always available.
Conversation history accumulates across run() calls by default.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable, Iterator

from ._sync import _SyncBridge
from .config import AgentConfig
from .context import check_context_window
from .conversation import ConversationManager, SlidingWindow, Session
from .circuit_breaker import CircuitBreaker, BreakerAction
from .engines import NativeEngine, ReactEngine, EngineResult, ToolCall
from .hooks import HookRegistry, HookContext, HookEvent
from .memory import Memory, make_memory_tools
from .messages import Message
from .model_info import ModelInfo, fetch_model_info
from .providers.ollama import OllamaProvider
from .sanitize import sanitize_tool_output, truncate_tool_output
from .skills import load_skills, build_skill_context, BUNDLED_SKILLS_DIR
from .telemetry import Metrics
from .events import (
    RunStartEvent, TokenEvent, ToolCallEvent, ToolResultEvent,
    ValidationErrorEvent, RetryEvent, IterationEvent, RunCompleteEvent, RunEvent,
)
from .providers import StreamChunk
from .tool import Tool, ToolResult
from .validator import Validator, ValidationOk, ValidationError


class Agent:
    """
    A local-first AI agent with guardrails, built-in telemetry, and memory.

    Usage:
        # Multi-turn by default
        agent = Agent(model="qwen3:8b", tools=[weather])
        agent.run("What's the weather in Tokyo?")
        agent.run("Convert that to Celsius")  # remembers Tokyo

        # Custom conversation strategy
        from freeagent.conversation import TokenWindow
        agent = Agent(model="qwen3:4b", conversation=TokenWindow(max_tokens=3000))

        # Persistent session
        agent = Agent(model="qwen3:8b", session="my-chat")

        # No conversation (each run independent)
        agent = Agent(model="qwen3:8b", conversation=None)
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        system_prompt: str = "You are a helpful assistant.",
        tools: list[Tool] = None,
        config: AgentConfig = None,
        provider=None,
        skills: list = None,
        conversation: ConversationManager | None = "default",
        session: str | None = None,
        auto_tune: bool = True,
        bundled_skills: bool | None = None,
        memory_tool: bool | None = None,
        **kwargs,
    ):
        self.config = config or AgentConfig()
        self.config.model = model
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)

        self.system_prompt = system_prompt

        # Model info — detect from Ollama if available
        self.model_info: ModelInfo | None = None
        if auto_tune:
            self.model_info = self._detect_model_info(model)

        # Auto-tune: determine effective bundled_skills and memory_tool
        use_bundled_skills = bundled_skills if bundled_skills is not None else True
        use_memory_tool = memory_tool if memory_tool is not None else True

        if auto_tune and self.model_info:
            # Small models: strip bundled skills and memory tool unless user explicitly set them
            if self.model_info.is_small:
                if bundled_skills is None:
                    use_bundled_skills = False
                if memory_tool is None:
                    use_memory_tool = False
            # Use detected context length
            if self.model_info.context_length > 0:
                self.config.context_window = self.model_info.context_length

        # Memory — markdown-backed, always on
        self.memory = Memory(memory_dir=kwargs.pop("memory_dir", None))

        # Memory tools — agent can read/write/search/list memory files
        if use_memory_tool:
            memory_tools = make_memory_tools(self.memory)
            self.tools = (tools or []) + memory_tools
        else:
            self.tools = tools or []

        # Skills — bundled skills load unless disabled, user skills extend them
        skill_sources = []
        if use_bundled_skills:
            skill_sources.append(BUNDLED_SKILLS_DIR)
        if skills:
            skill_sources.extend(skills)
        self.skills = load_skills(skill_sources) if skill_sources else []

        # Provider — use custom if given, otherwise default to Ollama
        if provider is not None:
            self.provider = provider
        else:
            self.provider = OllamaProvider(
                model=model,
                base_url=self.config.ollama_base_url,
            )

        # Engine selection — use model_info.supports_native_tools if available
        supports_tools = False
        if self.model_info and self.model_info.supports_native_tools:
            supports_tools = True
        elif self.config.supports_native_tools(model):
            supports_tools = True

        if self.tools and supports_tools:
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

        # Conversation — default is SlidingWindow(20), None disables
        if conversation == "default":
            self.conversation = SlidingWindow(max_turns=20)
        else:
            self.conversation = conversation

        # Session — optional persistence
        self._session: Session | None = None
        if session:
            self._session = Session(session)
            if self.conversation and self._session.exists:
                self._session.restore(self.conversation)

    # ── Model detection ─────────────────────────────────

    def _detect_model_info(self, model: str) -> ModelInfo | None:
        """Detect model info from Ollama /api/show. Returns None on failure."""
        try:
            return _SyncBridge.run(
                fetch_model_info(model, self.config.ollama_base_url)
            )
        except Exception:
            return None

    # ── Hook registration ────────────────────────────────

    def on(self, event: str | HookEvent, callback: Callable = None):
        """
        Register a hook. Works as decorator or direct call.

        @agent.on("before_tool")
        def my_hook(ctx):
            print(ctx.tool_name)
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

    # ── System Prompt ────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Assemble system prompt with skills and memory."""
        system = self.system_prompt

        skill_context = build_skill_context(self.skills)
        if skill_context:
            system = f"{system}\n\n{skill_context}"

        mem_context = self.memory.to_system_prompt()
        if mem_context:
            system = f"{system}\n\n{mem_context}"

        return system

    # ── Run ──────────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """Run the agent synchronously."""
        return _SyncBridge.run(self.arun(user_input))

    async def arun(self, user_input: str) -> str:
        """Run the agent asynchronously. Internally consumes arun_stream."""
        result = ""
        async for event in self.arun_stream(user_input):
            if isinstance(event, TokenEvent):
                result += event.text
            elif isinstance(event, RunCompleteEvent):
                result = event.response
        return result

    def run_stream(self, user_input: str) -> Iterator[RunEvent]:
        """Stream events synchronously. Uses SyncBridge to convert async iterator."""
        _SyncBridge._ensure_loop()
        loop = _SyncBridge._loop
        queue = asyncio.Queue()
        _SENTINEL = object()

        async def _producer():
            try:
                async for event in self.arun_stream(user_input):
                    await queue.put(event)
            finally:
                await queue.put(_SENTINEL)

        future = asyncio.run_coroutine_threadsafe(_producer(), loop)

        while True:
            item = asyncio.run_coroutine_threadsafe(queue.get(), loop).result()
            if item is _SENTINEL:
                break
            yield item

        # Propagate any exception from the producer
        future.result()

    async def arun_stream(self, user_input: str) -> AsyncIterator[RunEvent]:
        """Run the agent asynchronously, yielding semantic events."""
        start = time.monotonic()
        self.breaker.reset()

        # ── Telemetry: start run
        self.metrics.start_run(user_input, self.config.model, self._mode)

        yield RunStartEvent(model=self.config.model, mode=self._mode)

        # Fire before_run hook
        ctx = self._fire(HookEvent.BEFORE_RUN, user_input=user_input)
        if ctx.override_response is not None:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.end_run(ctx.override_response, elapsed)
            yield RunCompleteEvent(
                response=ctx.override_response, elapsed_ms=elapsed,
                metrics={"iterations": 0, "tool_calls": 0},
            )
            return

        # Build system prompt (skills + memory refreshed every turn)
        system = self._build_system_prompt()

        # Build messages via conversation manager (or fresh if no manager)
        if self.conversation:
            messages = self.conversation.prepare(system, user_input)
        else:
            messages = [Message.system(system), Message.user(user_input)]

        # Simple chat (no tools)
        if not self.tools or self.engine is None:
            self.metrics.record_model_call(0)
            result = ""
            if hasattr(self.provider, 'chat_stream'):
                async for chunk in self.provider.chat_stream(
                    messages, temperature=self.config.temperature
                ):
                    if chunk.content:
                        result += chunk.content
                        yield TokenEvent(text=chunk.content, iteration=0)
            else:
                response = await self.provider.chat(
                    messages, temperature=self.config.temperature
                )
                result = response.content
                yield TokenEvent(text=result, iteration=0)
            messages.append(Message.assistant(result))
        else:
            # Agent loop with timeout
            try:
                result = ""
                async with asyncio.timeout(self.config.timeout_seconds):
                    async for event in self._agent_loop_stream(messages):
                        if isinstance(event, TokenEvent):
                            result += event.text
                        elif isinstance(event, RunCompleteEvent):
                            result = event.response
                        yield event
            except (asyncio.TimeoutError, TimeoutError):
                self.metrics.record_timeout()
                self._fire(HookEvent.ON_TIMEOUT, user_input=user_input)
                result = self._graceful_timeout(messages)

        elapsed = (time.monotonic() - start) * 1000

        # ── Conversation: commit messages for next turn
        if self.conversation:
            self.conversation.commit(messages)

        # ── Session: persist if enabled
        if self._session and self.conversation:
            self._session.save(self.conversation)

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

        last = self.metrics.last_run
        yield RunCompleteEvent(
            response=result,
            elapsed_ms=elapsed,
            metrics={
                "iterations": last.iterations if last else 0,
                "tool_calls": last.tool_call_count if last else 0,
                "model_calls": last.model_calls if last else 0,
            },
        )

    async def _agent_loop(self, messages: list[Message]) -> str:
        """The core reason -> act -> observe loop. Non-streaming."""
        result = ""
        async for event in self._agent_loop_stream(messages):
            if isinstance(event, TokenEvent):
                result += event.text
            elif isinstance(event, RunCompleteEvent):
                result = event.response
        return result

    async def _agent_loop_stream(self, messages: list[Message]) -> AsyncIterator[RunEvent]:
        """The core reason -> act -> observe loop, yielding events."""
        retries_remaining = self.config.max_retries

        for iteration in range(self.config.max_iterations):
            yield IterationEvent(iteration=iteration)

            # ── Context window check: prune if over threshold
            messages = check_context_window(messages, self.config)

            # Fire before_model hook
            self._fire(HookEvent.BEFORE_MODEL, messages=messages, iteration=iteration)

            # ── Telemetry: model call
            self.metrics.record_model_call(iteration)

            # Get next action from engine
            try:
                result = await self.engine.execute(
                    messages=messages,
                    tools=self.tools,
                    temperature=self.config.temperature,
                )
            except ConnectionError:
                fallback = self._try_fallback()
                if fallback:
                    result = await self.engine.execute(
                        messages=messages,
                        tools=self.tools,
                        temperature=self.config.temperature,
                    )
                else:
                    raise

            # Fire after_model hook
            self._fire(
                HookEvent.AFTER_MODEL,
                model_response=result.content if not result.is_tool_call else result.tool_name,
                iteration=iteration,
            )

            # ── Text response (final answer) ──
            if not result.is_tool_call:
                messages.append(Message.assistant(result.content))
                # Yield the final text as tokens (single chunk from non-streaming engine)
                if result.content:
                    yield TokenEvent(text=result.content, iteration=iteration)
                return

            # ── Tool call(s) — handle single or parallel ──
            calls_to_execute = result.tool_calls or [
                ToolCall(name=result.tool_name, args=result.tool_args)
            ]

            # Validate all calls
            validated = []
            had_error = False
            for tc in calls_to_execute:
                validation = self.validator.validate(tc.name, tc.args)

                if isinstance(validation, ValidationError):
                    self.metrics.record_validation_error(tc.name)
                    yield ValidationErrorEvent(
                        tool_name=tc.name, errors=validation.errors,
                    )
                    self._fire(
                        HookEvent.ON_VALIDATION_ERROR,
                        tool_name=tc.name, args=tc.args,
                        errors=validation.errors, schema=validation.schema,
                        retry_count=self.config.max_retries - retries_remaining,
                    )
                    messages.append(Message.tool_error(
                        tc.name, validation.errors, validation.schema,
                    ))
                    retries_remaining -= 1
                    retry_count = self.config.max_retries - retries_remaining
                    self.metrics.record_retry(tc.name, retry_count)
                    yield RetryEvent(tool_name=tc.name, retry_count=retry_count)
                    self._fire(
                        HookEvent.ON_RETRY, tool_name=tc.name,
                        retry_count=retry_count,
                    )
                    had_error = True
                else:
                    validated.append((tc, validation))

            if had_error and not validated:
                if retries_remaining <= 0:
                    messages.append(Message.system(
                        "Tool calls keep failing. Please provide your "
                        "best answer based on what you know."
                    ))
                continue

            # Circuit breaker check for each call
            skip_loop = False
            for tc, validation in validated:
                breaker_result = self.breaker.check(tc.name, validation.args)
                if breaker_result.action == BreakerAction.LOOP_DETECTED:
                    self.metrics.record_loop_detected(tc.name)
                    self._fire(HookEvent.ON_LOOP, tool_name=tc.name, args=validation.args)
                    messages.append(Message.system(
                        f"STOP. {breaker_result.reason} "
                        "Give your best answer with the information gathered so far."
                    ))
                    skip_loop = True
                    break
                if breaker_result.action == BreakerAction.MAX_ITERATIONS:
                    self.metrics.record_max_iterations(iteration)
                    self._fire(HookEvent.ON_MAX_ITER, iteration=iteration)
                    partial = self._partial_answer(messages)
                    yield TokenEvent(text=partial, iteration=iteration)
                    return

            if skip_loop:
                continue

            # Emit tool call events
            for tc, _ in validated:
                yield ToolCallEvent(name=tc.name, args=tc.args)

            # Execute tools (concurrently if multiple)
            async def _exec_one(tc: ToolCall, validation: ValidationOk):
                ctx = self._fire(
                    HookEvent.BEFORE_TOOL, tool_name=tc.name,
                    args=validation.args, iteration=iteration,
                )
                if ctx.skip:
                    return tc, None

                self.metrics.start_tool(tc.name, validation.args)
                try:
                    tool_result = await validation.tool.execute(**validation.args)
                except Exception as e:
                    self._fire(HookEvent.ON_ERROR, tool_name=tc.name, error=e)
                    tool_result = ToolResult.fail(str(e))

                self.metrics.end_tool(
                    tool_name=tc.name, args=validation.args,
                    success=tool_result.success,
                    result_preview=tool_result.to_message()[:100],
                    error=tool_result.error or "",
                )
                self._fire(
                    HookEvent.AFTER_TOOL, tool_name=tc.name,
                    args=validation.args, result=tool_result, iteration=iteration,
                )
                return tc, tool_result

            if len(validated) == 1:
                results = [await _exec_one(*validated[0])]
            else:
                results = await asyncio.gather(
                    *[_exec_one(tc, v) for tc, v in validated]
                )

            # Emit tool result events
            for tc, tool_result in results:
                if tool_result is None:
                    continue
                duration = 0.0
                # Get duration from the last matching tool call record
                if self.metrics._current:
                    for tcr in reversed(self.metrics._current.tool_calls):
                        if tcr.name == tc.name:
                            duration = tcr.duration_ms
                            break
                yield ToolResultEvent(
                    name=tc.name,
                    result=tool_result.to_message()[:200],
                    success=tool_result.success,
                    duration_ms=duration,
                )

            # Build assistant message with all tool calls
            all_tool_calls = [{
                "function": {"name": tc.name, "arguments": tc.args}
            } for tc, _ in validated]
            messages.append(Message.assistant(
                f"Calling {', '.join(tc.name for tc, _ in validated)}...",
                tool_calls=all_tool_calls,
            ))

            # Append tool results
            for tc, tool_result in results:
                if tool_result is None:
                    continue
                tool_output = tool_result.to_message()
                tool_output = sanitize_tool_output(tool_output)
                tool_output = truncate_tool_output(
                    tool_output,
                    self.config.max_tool_result_chars,
                    self.config.max_tool_result_strategy,
                )
                messages.append(Message.tool_result(tc.name, tool_output))

            retries_remaining = self.config.max_retries

        partial = self._partial_answer(messages)
        yield TokenEvent(text=partial, iteration=self.config.max_iterations - 1)

    # ── Model fallback ────────────────────────────────────

    def _try_fallback(self) -> bool:
        """Try to switch to a fallback model. Returns True if switched."""
        for fallback in self.config.fallback_models:
            if fallback != self.config.model:
                self.config.model = fallback
                self.provider = OllamaProvider(
                    model=fallback,
                    base_url=self.config.ollama_base_url,
                )
                if self._mode == "native":
                    self.engine = NativeEngine(self.provider)
                elif self._mode == "react":
                    self.engine = ReactEngine(self.provider)
                return True
        return False

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
        conv = ""
        if self.conversation:
            conv = f", turns={self.conversation.turn_count}"
        mem = f", memory={len(self.memory)}" if len(self.memory) > 0 else ""
        return (
            f"Agent(model='{self.config.model}', "
            f"mode='{self._mode}', "
            f"tools={[t.name for t in self.tools]}{conv}{mem})"
        )
