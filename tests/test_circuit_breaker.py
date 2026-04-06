"""Tests for the circuit breaker — loop detection, max iterations, reset."""

from freeagent.circuit_breaker import CircuitBreaker, BreakerAction
from freeagent.config import AgentConfig


def _make_breaker(max_iter=10, loop_threshold=3):
    config = AgentConfig()
    config.max_iterations = max_iter
    config.loop_threshold = loop_threshold
    return CircuitBreaker(config)


class TestLoopDetection:
    def test_no_loop_different_args(self):
        breaker = _make_breaker()
        for i in range(5):
            result = breaker.check("tool", {"x": i})
            assert result.action == BreakerAction.CONTINUE

    def test_loop_detected_same_args(self):
        breaker = _make_breaker(loop_threshold=3)
        # threshold=3 means: trigger when repeats (count of previous identical) >= 3
        # So we need 4 calls: first 3 build history, 4th sees repeats=3
        breaker.check("tool", {"x": 1})
        breaker.check("tool", {"x": 1})
        breaker.check("tool", {"x": 1})
        result = breaker.check("tool", {"x": 1})
        assert result.action == BreakerAction.LOOP_DETECTED
        assert "stuck" in result.reason.lower()

    def test_different_tools_no_loop(self):
        breaker = _make_breaker(loop_threshold=2)
        breaker.check("tool_a", {"x": 1})
        result = breaker.check("tool_b", {"x": 1})
        assert result.action == BreakerAction.CONTINUE


class TestMaxIterations:
    def test_max_iterations_reached(self):
        breaker = _make_breaker(max_iter=3)
        breaker.check("a", {"x": 1})
        breaker.check("b", {"x": 2})
        result = breaker.check("c", {"x": 3})
        assert result.action == BreakerAction.MAX_ITERATIONS

    def test_under_max_continues(self):
        breaker = _make_breaker(max_iter=5)
        for i in range(4):
            result = breaker.check("tool", {"x": i})
            assert result.action == BreakerAction.CONTINUE


class TestReset:
    def test_reset_clears_history(self):
        breaker = _make_breaker(loop_threshold=2)
        breaker.check("tool", {"x": 1})
        breaker.reset()
        # After reset, same call should be fine
        result = breaker.check("tool", {"x": 1})
        assert result.action == BreakerAction.CONTINUE

    def test_reset_clears_iteration_count(self):
        breaker = _make_breaker(max_iter=2)
        breaker.check("a", {})
        breaker.reset()
        result = breaker.check("a", {})
        assert result.action == BreakerAction.CONTINUE
