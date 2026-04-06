"""Tests for skills — frontmatter parsing, loading, context building."""

import tempfile
from pathlib import Path

from freeagent.skills import (
    parse_frontmatter, load_skills, build_skill_context,
    Skill, BUNDLED_SKILLS_DIR,
)


class TestParseFrontmatter:
    def test_basic_frontmatter(self):
        content = "---\nname: test\nversion: 1\n---\nBody text"
        meta, body = parse_frontmatter(content)
        assert meta["name"] == "test"
        assert meta["version"] == 1
        assert "Body text" in body

    def test_no_frontmatter(self):
        content = "Just body text"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_inline_list(self):
        content = "---\ntools: [weather, calc, search]\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta["tools"] == ["weather", "calc", "search"]

    def test_boolean_values(self):
        content = "---\nauto_load: true\narchived: false\n---\n"
        meta, _ = parse_frontmatter(content)
        assert meta["auto_load"] is True
        assert meta["archived"] is False

    def test_quoted_string(self):
        content = '---\nname: "my skill"\n---\n'
        meta, _ = parse_frontmatter(content)
        assert meta["name"] == "my skill"

    def test_float_number(self):
        content = "---\nversion: 1.5\n---\n"
        meta, _ = parse_frontmatter(content)
        assert meta["version"] == 1.5

    def test_empty_frontmatter(self):
        content = "---\n---\nBody only"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert "Body only" in body


class TestLoadSkills:
    def test_load_bundled_skills(self):
        skills = load_skills([BUNDLED_SKILLS_DIR])
        assert len(skills) >= 2
        names = {s.name for s in skills}
        assert "general-assistant" in names
        assert "tool-user" in names

    def test_load_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill
            skill_dir = Path(tmpdir) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: my-skill\ndescription: Test skill\n---\nDo stuff."
            )
            skills = load_skills([tmpdir])
            assert len(skills) == 1
            assert skills[0].name == "my-skill"
            assert skills[0].instructions == "Do stuff."

    def test_duplicate_name_last_wins(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for d, desc in [(d1, "first"), (d2, "second")]:
                sd = Path(d) / "same-name"
                sd.mkdir()
                (sd / "SKILL.md").write_text(
                    f"---\nname: same-name\ndescription: {desc}\n---\n{desc}"
                )
            skills = load_skills([d1, d2])
            assert len(skills) == 1
            assert skills[0].description == "second"

    def test_skill_object_passthrough(self):
        s = Skill(name="inline", description="Inline skill", instructions="Be nice.")
        skills = load_skills([s])
        assert len(skills) == 1
        assert skills[0].name == "inline"

    def test_nonexistent_directory_ignored(self):
        skills = load_skills(["/nonexistent/path"])
        assert skills == []


class TestBuildSkillContext:
    def test_empty_skills(self):
        assert build_skill_context([]) == ""

    def test_basic_context(self):
        skills = [Skill(name="test", description="Test", instructions="Do things.")]
        ctx = build_skill_context(skills)
        assert "## Active Skills" in ctx
        assert "test" in ctx
        assert "Do things." in ctx

    def test_max_chars_budget(self):
        skills = [
            Skill(name=f"skill-{i}", instructions="x" * 100)
            for i in range(10)
        ]
        ctx = build_skill_context(skills, max_chars=300)
        assert "omitted" in ctx
        assert len(ctx) <= 500  # some overhead for markers

    def test_no_limit(self):
        skills = [
            Skill(name=f"skill-{i}", instructions="x" * 100)
            for i in range(5)
        ]
        ctx = build_skill_context(skills, max_chars=0)
        assert "omitted" not in ctx
