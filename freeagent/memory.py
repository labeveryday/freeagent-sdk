"""
Memory — markdown-based, directory-backed, always on.

Memory is stored as human-readable markdown files with frontmatter.
The agent gets built-in tools to read, write, search, and list memories.
Only the index and auto_load files go into the system prompt — everything
else is pulled on demand via tools. Token-efficient for small models.

Directory structure:
    .freeagent/memory/
    ├── MEMORY.md          # Index — lists all memory files
    ├── user.md            # User preferences (auto_load: true)
    ├── facts.md           # Accumulated facts
    ├── context.md         # Current project context
    └── 2026-04-05.md      # Daily log

MEMORY.md format:
    ---
    name: memory-index
    type: index
    ---

    ## Memory Files
    - **user.md** — User preferences and identity
    - **facts.md** — Facts learned during conversations

Individual memory file:
    ---
    name: user-preferences
    type: user
    description: User identity and preferences
    auto_load: true
    ---

    - Name: Du'An
    - Preferred units: metric

Usage:
    # Just works — .freeagent/memory/ in cwd
    agent = Agent(model="qwen3:8b")
    agent.memory.write("user.md", "- Name: Du'An\\n- Units: metric")
    agent.memory.read("user.md")

    # Custom location
    agent = Agent(model="qwen3:8b", memory_dir="~/.freeagent/memory")
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .skills import parse_frontmatter


# ── Default workspace ─────────────────────────────────────

DEFAULT_MEMORY_DIR = ".freeagent/memory"

_INDEX_TEMPLATE = """---
name: memory-index
type: index
updated: {date}
---

## Memory Files

This is the index of all memory files. Use `memory_list` to see available files,
or `memory_read` to read a specific file.
"""

_USER_TEMPLATE = """---
name: user-preferences
type: user
description: User identity and preferences
auto_load: true
updated: {date}
---

"""


class Memory:
    """
    Markdown-backed memory store.

    Files live in a directory. Each is a .md file with optional frontmatter.
    The index (MEMORY.md) and files with auto_load: true are injected into
    the system prompt. Everything else is accessible via agent memory tools.
    """

    def __init__(self, memory_dir: str | Path | None = None):
        if memory_dir is not None:
            self._dir = Path(memory_dir).expanduser().resolve()
        else:
            self._dir = Path(DEFAULT_MEMORY_DIR).resolve()

        # Don't create the directory on init — only on first write
        self._initialized = False

    # ── Core API (used by agent tools) ────────────────────

    def read(self, filename: str) -> str:
        """Read a memory file. Returns the full content (frontmatter + body)."""
        path = self._resolve(filename)
        if not path.is_file():
            return f"[Memory file '{filename}' not found]"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return f"[Error reading '{filename}']"

    def read_body(self, filename: str) -> str:
        """Read just the body of a memory file (no frontmatter)."""
        content = self.read(filename)
        if content.startswith("["):
            return content  # error message
        _, body = parse_frontmatter(content)
        return body.strip()

    def write(self, filename: str, content: str, meta: dict | None = None) -> str:
        """
        Write a memory file. Creates or overwrites.
        If meta is provided, generates frontmatter. Otherwise writes content as-is.
        """
        self._ensure_dir()
        path = self._resolve(filename)

        if meta:
            meta.setdefault("updated", datetime.now().strftime("%Y-%m-%d"))
            fm_lines = ["---"]
            for k, v in meta.items():
                if isinstance(v, bool):
                    fm_lines.append(f"{k}: {'true' if v else 'false'}")
                elif isinstance(v, list):
                    fm_lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
                else:
                    fm_lines.append(f"{k}: {v}")
            fm_lines.append("---\n")
            full_content = "\n".join(fm_lines) + "\n" + content
        else:
            full_content = content

        try:
            path.write_text(full_content, encoding="utf-8")
            self._update_index(filename)
            return f"[Saved to {filename}]"
        except OSError as e:
            return f"[Error writing '{filename}': {e}]"

    def append(self, filename: str, content: str) -> str:
        """Append content to an existing memory file. Creates if doesn't exist."""
        self._ensure_dir()
        path = self._resolve(filename)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content + "\n")
            self._update_index(filename)
            return f"[Appended to {filename}]"
        except OSError as e:
            return f"[Error appending to '{filename}': {e}]"

    def search(self, query: str) -> str:
        """Search across all memory files for lines matching the query."""
        if not self._dir.is_dir():
            return "[No memory files yet]"

        results = []
        query_lower = query.lower()

        for path in sorted(self._dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
                _, body = parse_frontmatter(content)

                matches = []
                for line in body.split("\n"):
                    if query_lower in line.lower():
                        matches.append(line.strip())

                if matches:
                    results.append(f"**{path.name}:**")
                    for m in matches[:5]:  # max 5 matches per file
                        results.append(f"  {m}")
            except OSError:
                continue

        if not results:
            return f"[No matches for '{query}']"
        return "\n".join(results)

    def list_files(self) -> str:
        """List all memory files with their descriptions."""
        if not self._dir.is_dir():
            return "[No memory files yet]"

        files = []
        for path in sorted(self._dir.glob("*.md")):
            meta, body = parse_frontmatter(
                path.read_text(encoding="utf-8")
            )
            desc = meta.get("description", "")
            auto = " (auto-loaded)" if meta.get("auto_load") else ""
            name = path.name
            if desc:
                files.append(f"- **{name}**{auto} — {desc}")
            else:
                # Use first non-empty body line as description
                first_line = ""
                for line in body.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        first_line = line[:80]
                        break
                files.append(f"- **{name}**{auto} — {first_line}")

        if not files:
            return "[No memory files yet]"
        return "\n".join(files)

    def delete(self, filename: str) -> str:
        """Delete a memory file."""
        path = self._resolve(filename)
        if filename == "MEMORY.md":
            return "[Cannot delete the memory index]"
        if not path.is_file():
            return f"[File '{filename}' not found]"
        try:
            path.unlink()
            self._update_index(filename, removed=True)
            return f"[Deleted {filename}]"
        except OSError as e:
            return f"[Error deleting '{filename}': {e}]"

    # ── Programmatic helpers (used by framework) ──────────

    def set(self, key: str, value: Any, source: str = "agent") -> None:
        """Quick KV-style write — appends to facts.md."""
        self.append("facts.md", f"- {key}: {value}")

    def get(self, key: str, default: Any = None) -> Any:
        """Quick KV-style read — searches facts.md for a key."""
        content = self.read_body("facts.md")
        if content.startswith("["):
            return default
        for line in content.split("\n"):
            if line.strip().startswith(f"- {key}:"):
                return line.split(":", 1)[1].strip()
        return default

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    # ── System prompt injection ───────────────────────────

    def to_system_prompt(self, max_chars: int = 1500) -> str:
        """
        Build the memory section of the system prompt.

        Loads:
        1. MEMORY.md index (always, if exists)
        2. Any file with auto_load: true in frontmatter
        3. Truncates to max_chars total

        Everything else is accessible via memory tools.
        """
        if not self._dir.is_dir():
            return ""

        parts = []
        total = 0

        # Load index
        index_path = self._dir / "MEMORY.md"
        if index_path.is_file():
            _, body = parse_frontmatter(index_path.read_text(encoding="utf-8"))
            body = body.strip()
            if body:
                parts.append(f"## Memory Index\n{body}")
                total += len(parts[-1])

        # Load auto_load files
        for path in sorted(self._dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            try:
                content = path.read_text(encoding="utf-8")
                meta, body = parse_frontmatter(content)
                if meta.get("auto_load"):
                    section = f"### {meta.get('name', path.stem)}\n{body.strip()}"
                    if total + len(section) > max_chars:
                        break
                    parts.append(section)
                    total += len(section)
            except OSError:
                continue

        if not parts:
            return ""

        return "## Your Memory\n\n" + "\n\n".join(parts)

    # ── Daily log ──────────────────────────────────────���──

    def log(self, entry: str) -> None:
        """Append to today's daily log."""
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}.md"
        path = self._resolve(filename)

        if not path.is_file():
            # Create with frontmatter
            self.write(filename, f"## {today}\n\n{entry}\n", meta={
                "name": f"daily-log-{today}",
                "type": "log",
                "description": f"Conversation log for {today}",
            })
        else:
            timestamp = datetime.now().strftime("%H:%M")
            self.append(filename, f"\n### {timestamp}\n{entry}")

    # ── Internal ──────────────────────────────────────────

    def _resolve(self, filename: str) -> Path:
        """Resolve a filename to a full path in the memory directory."""
        # Prevent directory traversal
        clean = Path(filename).name
        return self._dir / clean

    def _ensure_dir(self):
        """Create the memory directory and index on first write."""
        if self._initialized:
            return
        self._dir.mkdir(parents=True, exist_ok=True)

        index = self._dir / "MEMORY.md"
        if not index.is_file():
            today = datetime.now().strftime("%Y-%m-%d")
            index.write_text(_INDEX_TEMPLATE.format(date=today), encoding="utf-8")

        self._initialized = True

    def _update_index(self, filename: str, removed: bool = False):
        """Update MEMORY.md index when a file is added/removed."""
        index_path = self._dir / "MEMORY.md"
        if not index_path.is_file():
            return

        content = index_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        if removed:
            # Remove the line referencing this file
            lines = [l for l in body.split("\n") if f"**{filename}**" not in l]
            body = "\n".join(lines)
        else:
            # Add if not already listed
            if f"**{filename}**" not in body:
                # Get description from the file
                file_path = self._dir / filename
                desc = ""
                if file_path.is_file():
                    file_meta, _ = parse_frontmatter(
                        file_path.read_text(encoding="utf-8")
                    )
                    desc = file_meta.get("description", "")

                entry = f"- **{filename}** — {desc}" if desc else f"- **{filename}**"
                body = body.rstrip() + "\n" + entry + "\n"

        # Rebuild with updated date
        meta["updated"] = datetime.now().strftime("%Y-%m-%d")
        fm = "---\n"
        for k, v in meta.items():
            fm += f"{k}: {v}\n"
        fm += "---\n"

        index_path.write_text(fm + "\n" + body, encoding="utf-8")

    @property
    def exists(self) -> bool:
        return self._dir.is_dir()

    def __repr__(self) -> str:
        if not self._dir.is_dir():
            return f"Memory(dir={self._dir}, empty)"
        count = len(list(self._dir.glob("*.md")))
        return f"Memory(dir={self._dir}, files={count})"

    def __len__(self) -> int:
        if not self._dir.is_dir():
            return 0
        return len(list(self._dir.glob("*.md")))

    def __contains__(self, filename: str) -> bool:
        return self._resolve(filename).is_file()


# ── Memory Tools (auto-added to agent) ───────────────────

def make_memory_tools(memory: Memory) -> list:
    """
    Create a single memory tool for the agent.
    One tool instead of five — saves ~250 tokens of tool spec overhead.
    """
    from .tool import tool as tool_decorator

    @tool_decorator(name="memory")
    def memory_tool(action: str, file: str = "", content: str = "", query: str = "") -> str:
        """Manage agent memory files. Actions: read, write, append, search, list.
        read: read a file (file required). write: create/update file (file + content required).
        append: add to file (file + content required). search: find text (query required).
        list: show all files."""
        action = action.lower().strip()
        if action == "read":
            if not file:
                return "[Error: 'file' required for read]"
            return memory.read_body(file)
        elif action == "write":
            if not file or not content:
                return "[Error: 'file' and 'content' required for write]"
            return memory.write(file, content, meta={
                "name": Path(file).stem,
                "type": "custom",
                "description": content.split("\n")[0][:80],
            })
        elif action == "append":
            if not file or not content:
                return "[Error: 'file' and 'content' required for append]"
            return memory.append(file, content)
        elif action == "search":
            if not query:
                return "[Error: 'query' required for search]"
            return memory.search(query)
        elif action == "list":
            return memory.list_files()
        else:
            return f"[Unknown action '{action}'. Use: read, write, append, search, list]"

    return [memory_tool]
