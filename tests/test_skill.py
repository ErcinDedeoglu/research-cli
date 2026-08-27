from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".grok" / "skills" / "research-cli" / "SKILL.md"


class SkillFileTests(unittest.TestCase):
    def test_skill_instructs_agents_to_run_this_cli(self) -> None:
        self.assertTrue(SKILL.is_file(), f"missing skill file: {SKILL}")
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"), "SKILL.md needs YAML frontmatter")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, "SKILL.md frontmatter is not closed")
        front = match.group(1)
        self.assertRegex(front, r"(?m)^name:\s*\S+")
        self.assertRegex(front, r"(?m)^description:\s*.+")
        body = text.lower()
        self.assertIn("research-cli", body)
        self.assertIn("bgpt", body)
        self.assertIn("brave", body)
        self.assertIn("exa", body)
        self.assertIn("firecrawl", body)
        self.assertIn("brave_api_key", body)
        self.assertIn("exa_api_key", body)
        self.assertIn("firecrawl_api_key", body)
        self.assertTrue(
            "not" in body and "mcp" in body,
            "skill must tell agents to use this CLI instead of MCP",
        )


if __name__ == "__main__":
    unittest.main()
