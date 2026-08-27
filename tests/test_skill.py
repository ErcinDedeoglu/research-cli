from __future__ import annotations

import argparse
import re
import shlex
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli import __version__  # noqa: E402
from research_cli.cli import build_parser  # noqa: E402
from research_cli.keys import (  # noqa: E402
    optional_bgpt_key,
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
)

SKILL = ROOT / "skills" / "research-cli" / "SKILL.md"
AGENTS = ROOT / "AGENTS.md"
ENV_EXAMPLE = ROOT / ".env.example"

ENV_NAMES = (
    "BGPT_API_KEY",
    "BRAVE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
)


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _example_lines(text: str) -> list[str]:
    blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
    lines: list[str] = []
    for block in blocks:
        for raw in block.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if tokens and tokens[0] in {"research-cli", "python"}:
                lines.append(line)
    return lines


def _example_argv(line: str) -> list[str]:
    tokens = shlex.split(line)
    if not tokens:
        raise ValueError(f"empty example: {line}")
    if tokens[0] not in {"research-cli", "python"}:
        raise ValueError(f"example must start with research-cli: {line}")
    if tokens[0] == "python":
        if len(tokens) < 4 or tokens[1] != "-m" or tokens[2] != "research_cli":
            raise ValueError(f"python example must be python -m research_cli: {line}")
        return tokens[3:]
    return tokens[1:]


def _leaf_paths(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        return {prefix} if prefix else set()
    paths: set[tuple[str, ...]] = set()
    for action in subs:
        for name, child in action.choices.items():
            paths |= _leaf_paths(child, prefix + (name,))
    return paths


def _option_flags(parser: argparse.ArgumentParser) -> set[str]:
    flags: set[str] = set()

    def walk(node: argparse.ArgumentParser) -> None:
        for action in node._actions:
            flags.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    walk(child)

    walk(parser)
    return flags


def _argv_command_path(argv: list[str], parser: argparse.ArgumentParser) -> tuple[str, ...]:
    args = parser.parse_args(argv)
    path: list[str] = []
    if getattr(args, "provider", None):
        path.append(args.provider)
    if getattr(args, "operation", None):
        path.append(args.operation)
    if getattr(args, "papers_op", None):
        path.append(args.papers_op)
    return tuple(path)


class SkillFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SKILL.is_file(), f"missing skill file: {SKILL}")
        self.text = _skill_text()
        self.parser = build_parser()

    def test_frontmatter_and_cli_not_mcp(self) -> None:
        self.assertTrue(self.text.startswith("---"))
        match = re.match(r"^---\n(.*?)\n---\n", self.text, re.S)
        self.assertIsNotNone(match)
        front = match.group(1)
        self.assertRegex(front, r"(?m)^name:\s*research-cli\s*$")
        self.assertRegex(
            front,
            rf"(?m)^version:\s*{re.escape(__version__)}\s*$",
        )
        self.assertRegex(front, r"(?m)^description:\s*.+")
        self.assertIn("version guard", self.text.lower())
        self.assertIn("install if missing", self.text.lower())
        self.assertIn("releases/latest/download", self.text)
        self.assertIn("command -v research-cli", self.text)
        body = self.text.lower()
        self.assertIn("research-cli", body)
        self.assertIn("python -m research_cli", body)
        self.assertTrue("mcp" in body and "do not" in body)

    def test_examples_parse_on_the_real_parser(self) -> None:
        lines = _example_lines(self.text)
        self.assertGreaterEqual(len(lines), len(_leaf_paths(self.parser)))
        covered: set[tuple[str, ...]] = set()
        for line in lines:
            argv = _example_argv(line)
            try:
                path = _argv_command_path(argv, self.parser)
            except SystemExit as exc:
                self.fail(f"skill example does not parse: {line}\n{exc}")
            self.assertTrue(path, f"example did not select a command: {line}")
            covered.add(path)
        missing = _leaf_paths(self.parser) - covered
        self.assertFalse(
            missing,
            "SKILL.md is missing an example for CLI operation(s): "
            + ", ".join(" ".join(path) for path in sorted(missing)),
        )
        extra = covered - _leaf_paths(self.parser)
        self.assertFalse(
            extra,
            "SKILL.md examples name operations the CLI does not have: "
            + ", ".join(" ".join(path) for path in sorted(extra)),
        )

    def test_flags_named_in_skill_exist_on_cli(self) -> None:
        mentioned = set(re.findall(r"(?<![`\w])(--[a-z][a-z0-9-]*)", self.text))
        mentioned.discard("--help")
        known = _option_flags(self.parser)
        unknown = mentioned - known
        self.assertFalse(
            unknown,
            f"SKILL.md documents flags the CLI does not accept: {sorted(unknown)}",
        )

    def test_env_keys_match_shipped_key_module(self) -> None:
        self.assertTrue(callable(optional_bgpt_key))
        self.assertTrue(callable(require_brave_key))
        self.assertTrue(callable(require_exa_key))
        self.assertTrue(callable(require_firecrawl_key))
        for name in ENV_NAMES:
            self.assertIn(
                f"`{name}`",
                self.text,
                f"SKILL.md must document env var {name} (from keys.py)",
            )
        self.assertIn("brave search", self.text.lower())
        example = ENV_EXAMPLE.read_text(encoding="utf-8")
        for name in ("BRAVE_API_KEY", "EXA_API_KEY", "FIRECRAWL_API_KEY", "BGPT_API_KEY"):
            self.assertIn(name, example)
        self.assertTrue(AGENTS.is_file(), f"missing {AGENTS}")
        agents = AGENTS.read_text(encoding="utf-8")
        self.assertIn("skills/research-cli/SKILL.md", agents)
        self.assertIn("mcp", agents.lower())


if __name__ == "__main__":
    unittest.main()
