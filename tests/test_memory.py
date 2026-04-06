"""Tests for memory — read/write/append/search/list, daily log, system prompt, KV helpers."""

import tempfile
from pathlib import Path

from freeagent.memory import Memory, make_memory_tools


class TestMemoryReadWrite:
    def _make_memory(self):
        tmpdir = tempfile.mkdtemp()
        return Memory(memory_dir=tmpdir), tmpdir

    def test_write_and_read(self):
        mem, _ = self._make_memory()
        mem.write("test.md", "Hello world")
        content = mem.read("test.md")
        assert "Hello world" in content

    def test_read_nonexistent(self):
        mem, _ = self._make_memory()
        result = mem.read("nope.md")
        assert "not found" in result.lower()

    def test_write_with_meta(self):
        mem, _ = self._make_memory()
        mem.write("facts.md", "Some facts", meta={
            "name": "facts",
            "type": "custom",
            "auto_load": True,
        })
        content = mem.read("facts.md")
        assert "auto_load: true" in content
        assert "Some facts" in content

    def test_read_body(self):
        mem, _ = self._make_memory()
        mem.write("facts.md", "Just the body", meta={"name": "facts"})
        body = mem.read_body("facts.md")
        assert body == "Just the body"
        assert "---" not in body


class TestMemoryAppend:
    def test_append_creates_file(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.append("notes.md", "Line 1")
        mem.append("notes.md", "Line 2")
        content = mem.read("notes.md")
        assert "Line 1" in content
        assert "Line 2" in content


class TestMemorySearch:
    def test_search_finds_match(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("facts.md", "Python is great\nJava is verbose")
        result = mem.search("Python")
        assert "Python is great" in result

    def test_search_no_match(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("facts.md", "Nothing here")
        result = mem.search("Rust")
        assert "No matches" in result

    def test_search_empty_memory(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        result = mem.search("anything")
        assert "No memory" in result or "No matches" in result


class TestMemoryList:
    def test_list_files(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("a.md", "File A", meta={"name": "a", "description": "First"})
        mem.write("b.md", "File B", meta={"name": "b", "description": "Second"})
        result = mem.list_files()
        assert "a.md" in result
        assert "b.md" in result

    def test_list_empty(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        result = mem.list_files()
        # Only MEMORY.md index or empty
        assert "No memory" in result or "MEMORY.md" in result


class TestMemoryDelete:
    def test_delete_file(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("temp.md", "Temporary")
        result = mem.delete("temp.md")
        assert "Deleted" in result
        assert "not found" in mem.read("temp.md").lower()

    def test_cannot_delete_index(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("dummy.md", "x")  # trigger dir creation
        result = mem.delete("MEMORY.md")
        assert "Cannot delete" in result


class TestSystemPrompt:
    def test_empty_memory(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        assert mem.to_system_prompt() == ""

    def test_auto_load_included(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("user.md", "- Name: Test", meta={
            "name": "user-prefs",
            "auto_load": True,
        })
        prompt = mem.to_system_prompt()
        assert "Name: Test" in prompt
        assert "Your Memory" in prompt

    def test_non_auto_load_excluded(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("private.md", "Secret stuff", meta={
            "name": "private",
            "auto_load": False,
        })
        prompt = mem.to_system_prompt()
        assert "Secret stuff" not in prompt


class TestDailyLog:
    def test_log_creates_daily_file(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.log("Test entry")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        content = mem.read(f"{today}.md")
        assert "Test entry" in content


class TestKVHelpers:
    def test_set_and_get(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.set("color", "blue")
        assert mem.get("color") == "blue"

    def test_get_default(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        assert mem.get("missing", "default") == "default"

    def test_has(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.set("exists", "yes")
        assert mem.has("exists")
        assert not mem.has("nope")


class TestMemoryContains:
    def test_contains(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        mem.write("test.md", "content")
        assert "test.md" in mem
        assert "nope.md" not in mem


class TestMemoryLen:
    def test_len(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        assert len(mem) == 0
        mem.write("a.md", "content")
        assert len(mem) >= 1  # includes MEMORY.md index


class TestDirectoryTraversal:
    def test_prevents_traversal(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        result = mem.read("../../etc/passwd")
        assert "not found" in result.lower()


class TestMemoryTools:
    def test_make_memory_tools_returns_tool(self):
        mem = Memory(memory_dir=tempfile.mkdtemp())
        tools = make_memory_tools(mem)
        assert len(tools) == 1
        assert tools[0].name == "memory"
