"""
Skills — markdown-based prompt extensions loaded from directories.

A skill is a directory containing a SKILL.md file with YAML frontmatter
and markdown instructions. Skills get injected into the agent's system
prompt automatically.

Structure:
    skills/
    ├── weather-assistant/
    │   └── SKILL.md
    ├── code-reviewer/
    │   ├── SKILL.md
    │   └── templates/         # supporting files
    └── nba-analyst/
        └── SKILL.md

SKILL.md format:
    ---
    name: weather-assistant
    description: Helps users check weather and plan activities
    version: 1.0
    tools: [weather, unit_converter]
    ---

    You are a weather assistant. Always check the weather tool before
    making recommendations. Convert temperatures when asked.

Usage:
    agent = Agent(
        model="qwen3:8b",
        tools=[weather, calculator],
        skills=["./skills"],
    )

Skills are loaded at agent init. The markdown body is injected into
the system prompt. Frontmatter provides metadata for the framework
(name, description, which tools the skill expects).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Bundled skills ship with the package
BUNDLED_SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass
class Skill:
    """A loaded skill with metadata and instructions."""
    name: str
    description: str = ""
    version: str = ""
    instructions: str = ""  # markdown body
    tools: list[str] = field(default_factory=list)  # tool names this skill uses
    path: Path | None = None  # directory path (for file references)

    def to_prompt(self) -> str:
        """Render this skill for injection into the system prompt."""
        parts = [f"### Skill: {self.name}"]
        if self.description:
            parts.append(self.description)
        if self.instructions:
            parts.append(self.instructions)
        return "\n".join(parts)


def load_skills(sources: list) -> list[Skill]:
    """
    Load skills from a mixed list of sources.

    Accepts:
        - str or Path → directory containing skill subdirectories
        - Skill object → used directly

    Returns list of loaded Skill objects. Duplicates by name: last wins.
    """
    loaded: dict[str, Skill] = {}

    for source in sources:
        if isinstance(source, Skill):
            loaded[source.name] = source
        elif isinstance(source, (str, Path)):
            path = Path(source).expanduser().resolve()
            if path.is_dir():
                for skill in _load_directory(path):
                    loaded[skill.name] = skill

    return list(loaded.values())


def build_skill_context(skills: list[Skill], max_chars: int = 0) -> str:
    """
    Build the system prompt section from loaded skills.

    Args:
        skills: List of Skill objects.
        max_chars: Max total characters for skill content (0 = no limit).
                   When exceeded, skills are included in order until budget runs out.
    """
    if not skills:
        return ""

    parts = ["## Active Skills\n"]
    total = len(parts[0])

    for skill in skills:
        section = skill.to_prompt()
        if max_chars > 0 and total + len(section) > max_chars:
            parts.append(f"\n[{len(skills) - len(parts) + 1} more skills omitted — context budget]")
            break
        parts.append(section)
        total += len(section)

    return "\n\n".join(parts)


# ── Loading ───────────────────────────────────────────────

def _load_directory(path: Path) -> list[Skill]:
    """Load all skills from subdirectories of the given path."""
    skills = []
    if not path.is_dir():
        return skills

    for child in sorted(path.iterdir()):
        if child.is_dir():
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                skill = _load_skill_file(skill_file, child)
                if skill:
                    skills.append(skill)

    return skills


def _load_skill_file(skill_file: Path, skill_dir: Path) -> Skill | None:
    """Load a single SKILL.md file into a Skill object."""
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None

    meta, body = parse_frontmatter(content)

    # Use directory name as fallback for skill name
    name = meta.get("name", skill_dir.name)

    return Skill(
        name=name,
        description=meta.get("description", ""),
        version=str(meta.get("version", "")),
        instructions=body.strip(),
        tools=_parse_list(meta.get("tools", [])),
        path=skill_dir,
    )


# ── Frontmatter Parser (no PyYAML dependency) ────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse YAML-like frontmatter from markdown content.
    Returns (metadata_dict, body_text).

    Supports simple key: value pairs and inline lists [a, b, c].
    No PyYAML dependency — handles the subset we need.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = content[match.end():]

    meta = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        colon_idx = line.find(":")
        if colon_idx == -1:
            continue

        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()

        # Parse inline list: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            meta[key] = [item.strip().strip("'\"") for item in items if item.strip()]
        # Parse quoted string
        elif (value.startswith('"') and value.endswith('"')) or \
             (value.startswith("'") and value.endswith("'")):
            meta[key] = value[1:-1]
        # Parse boolean
        elif value.lower() in ("true", "yes"):
            meta[key] = True
        elif value.lower() in ("false", "no"):
            meta[key] = False
        # Parse number
        elif value.replace(".", "", 1).isdigit():
            meta[key] = float(value) if "." in value else int(value)
        else:
            meta[key] = value

    return meta, body


def _parse_list(value: Any) -> list[str]:
    """Ensure a value is a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []
