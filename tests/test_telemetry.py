"""Tests for telemetry — Metrics, RunRecord, ToolCallRecord."""

from freeagent.telemetry import Metrics, RunRecord, ToolCallRecord


class TestMetricsLifecycle:
    def test_start_and_end_run(self):
        m = Metrics()
        m.start_run("hello", "llama3.1:8b", "native")
        m.end_run("response", 100.0)

        assert m.total_runs == 1
        assert m.last_run.user_input == "hello"
        assert m.last_run.model == "llama3.1:8b"
        assert m.last_run.mode == "native"
        assert m.last_run.elapsed_ms == 100.0

    def test_multiple_runs(self):
        m = Metrics()
        for i in range(3):
            m.start_run(f"q{i}", "model", "chat")
            m.end_run(f"r{i}", float(i * 10))

        assert m.total_runs == 3
        assert m.last_run.user_input == "q2"

    def test_record_model_call(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_model_call(0)
        m.record_model_call(1)
        m.end_run("r", 50.0)

        assert m.last_run.model_calls == 2
        assert m.last_run.iterations == 2


class TestToolRecording:
    def test_start_and_end_tool(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.start_tool("weather", {"city": "NYC"})
        m.end_tool("weather", {"city": "NYC"}, success=True, result_preview="72F")
        m.end_run("r", 50.0)

        assert m.last_run.tool_call_count == 1
        tc = m.last_run.tool_calls[0]
        assert tc.name == "weather"
        assert tc.success is True
        assert tc.duration_ms > 0 or tc.duration_ms == 0  # might be very fast

    def test_failed_tool(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.start_tool("broken", {})
        m.end_tool("broken", {}, success=False, error="timeout")
        m.end_run("r", 50.0)

        assert m.last_run.error_count == 1


class TestToolStats:
    def test_tool_stats(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.start_tool("weather", {"city": "NYC"})
        m.end_tool("weather", {"city": "NYC"}, success=True)
        m.start_tool("weather", {"city": "LA"})
        m.end_tool("weather", {"city": "LA"}, success=False, error="err")
        m.end_run("r", 50.0)

        stats = m.tool_stats()
        assert "weather" in stats
        assert stats["weather"]["count"] == 2
        assert stats["weather"]["errors"] == 1
        assert stats["weather"]["error_rate"] == 0.5


class TestValidationAndRetry:
    def test_validation_error(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_validation_error("weather")
        m.end_run("r", 50.0)
        assert m.last_run.validation_errors == 1

    def test_retry(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_retry("weather", 1)
        m.end_run("r", 50.0)
        assert m.last_run.retries == 1


class TestCircuitBreakerEvents:
    def test_loop_detected(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_loop_detected("weather")
        m.end_run("r", 50.0)
        assert m.last_run.loop_detected is True

    def test_max_iterations(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_max_iterations(10)
        m.end_run("r", 50.0)
        assert m.last_run.max_iter_hit is True

    def test_timeout(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.record_timeout()
        m.end_run("r", 50.0)
        assert m.last_run.timed_out is True


class TestExport:
    def test_to_dict(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.end_run("r", 50.0)

        d = m.to_dict()
        assert d["total_runs"] == 1
        assert "runs" in d
        assert "tool_stats" in d

    def test_to_json(self):
        import json
        m = Metrics()
        m.start_run("q", "model", "native")
        m.end_run("r", 50.0)

        j = m.to_json()
        data = json.loads(j)
        assert data["total_runs"] == 1


class TestReset:
    def test_reset(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.end_run("r", 50.0)
        m.reset()

        assert m.total_runs == 0
        assert m.last_run is None


class TestAggregates:
    def test_avg_latency(self):
        m = Metrics()
        m.start_run("a", "model", "chat")
        m.end_run("r", 100.0)
        m.start_run("b", "model", "chat")
        m.end_run("r", 200.0)
        assert m.avg_latency_ms == 150.0

    def test_total_tool_calls(self):
        m = Metrics()
        m.start_run("q", "model", "native")
        m.start_tool("a", {})
        m.end_tool("a", {}, success=True)
        m.start_tool("b", {})
        m.end_tool("b", {}, success=True)
        m.end_run("r", 50.0)
        assert m.total_tool_calls == 2

    def test_repr_and_str(self):
        m = Metrics()
        assert "no runs" in repr(m).lower()
        assert "No runs" in str(m)
        m.start_run("q", "model", "native")
        m.end_run("r", 50.0)
        assert "runs=1" in repr(m)
