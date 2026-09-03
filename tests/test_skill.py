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
from research_cli.cli import EPILOG, HELP_TOPICS, INSTALL_DOC_URL, build_parser  # noqa: E402
from research_cli.keys import (  # noqa: E402
    optional_bgpt_key,
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
    require_reddit_credentials,
    require_telegram_app,
    require_telegram_session,
    require_tgstat_session,
    require_x_credentials,
)

SKILL = ROOT / "skills" / "research-cli" / "SKILL.md"
INSTALL = ROOT / "skills" / "research-cli" / "INSTALL.md"
AGENTS = ROOT / "AGENTS.md"
ENV_EXAMPLE = ROOT / ".env.example"

ENV_NAMES = (
    "BGPT_API_KEY",
    "BRAVE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "X_AUTH_TOKEN",
    "X_CT0",
    "TGSTAT_IDR",
    "TGSTAT_SIRK",
    "TGSTAT_CSRK",
    "TGSTAT_SETTINGS",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION",
    "TELEGRAM_SESSION_FILE",
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


def _epilog_example_lines() -> list[str]:
    lines: list[str] = []
    for raw in EPILOG.splitlines():
        line = raw.strip()
        if not line.startswith("research-cli "):
            continue
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
        desc = front.lower()
        self.assertIn("must use", desc)
        self.assertIn("search", desc)
        self.assertIn("research", desc)
        self.assertIn("parallel", desc)
        self.assertIn("version guard", self.text.lower())
        self.assertIn("help install", self.text.lower())
        self.assertIn(INSTALL_DOC_URL, self.text)
        self.assertIn("INSTALL.md", self.text)
        self.assertNotIn("releases/latest/download", self.text)
        self.assertNotIn("command -v research-cli", self.text)
        self.assertNotIn("research-cli-Darwin-arm64", self.text)
        self.assertNotIn("pip install", self.text)
        self.assertNotIn("python -m research_cli", self.text)
        self.assertNotIn("zipapp", self.text.lower())
        body = self.text.lower()
        self.assertIn("research-cli", body)
        self.assertTrue("mcp" in body and "do not" in body)

    def test_install_doc_matches_help_install_topic(self) -> None:
        self.assertTrue(INSTALL.is_file(), f"missing install doc: {INSTALL}")
        doc = INSTALL.read_text(encoding="utf-8").strip()
        topic = HELP_TOPICS["install"].strip()
        self.assertEqual(
            doc,
            topic,
            "skills/research-cli/INSTALL.md must match cli HELP_TOPICS['install']",
        )
        self.assertIn("research-cli-Darwin-arm64", doc)
        self.assertIn("releases/latest/download", doc)
        self.assertIn("command -v research-cli", doc)
        self.assertTrue(
            INSTALL_DOC_URL.endswith("/skills/research-cli/INSTALL.md"),
            INSTALL_DOC_URL,
        )

    def test_examples_parse_on_the_real_parser(self) -> None:
        skill_lines = _example_lines(self.text)
        self.assertGreaterEqual(len(skill_lines), 7)
        skill_covered: set[tuple[str, ...]] = set()
        for line in skill_lines:
            argv = _example_argv(line)
            try:
                path = _argv_command_path(argv, self.parser)
            except SystemExit as exc:
                self.fail(f"skill example does not parse: {line}\n{exc}")
            self.assertTrue(path, f"example did not select a command: {line}")
            skill_covered.add(path)
        extra = skill_covered - _leaf_paths(self.parser)
        self.assertFalse(
            extra,
            "SKILL.md examples name operations the CLI does not have: "
            + ", ".join(" ".join(path) for path in sorted(extra)),
        )
        missing_skill = _leaf_paths(self.parser) - skill_covered
        self.assertFalse(
            missing_skill,
            "SKILL.md Commands is missing an example for CLI operation(s): "
            + ", ".join(" ".join(path) for path in sorted(missing_skill)),
        )
        for line in _epilog_example_lines():
            argv = _example_argv(line)
            try:
                path = _argv_command_path(argv, self.parser)
            except SystemExit as exc:
                self.fail(f"--help epilog example does not parse: {line}\n{exc}")
            self.assertTrue(path, f"epilog example did not select a command: {line}")

    def test_flags_named_in_skill_exist_on_cli(self) -> None:
        mentioned = set(re.findall(r"(?<![`\w])(--[a-z][a-z0-9-]*)", self.text))
        mentioned.discard("--help")
        known = _option_flags(self.parser)
        unknown = mentioned - known
        self.assertFalse(
            unknown,
            f"SKILL.md documents flags the CLI does not accept: {sorted(unknown)}",
        )

    def test_env_keys_documented_in_help_keys_topic(self) -> None:
        self.assertTrue(callable(optional_bgpt_key))
        self.assertTrue(callable(require_brave_key))
        self.assertTrue(callable(require_exa_key))
        self.assertTrue(callable(require_firecrawl_key))
        self.assertTrue(callable(require_reddit_credentials))
        self.assertTrue(callable(require_x_credentials))
        self.assertTrue(callable(require_telegram_app))
        self.assertTrue(callable(require_telegram_session))
        self.assertTrue(callable(require_tgstat_session))
        keys_topic = HELP_TOPICS["keys"]
        self.assertIn(".config/research-cli/env", keys_topic)
        for name in ENV_NAMES:
            self.assertIn(
                name,
                keys_topic,
                f"help keys topic must document env var {name} (from keys.py)",
            )
        self.assertIn("help keys", self.text.lower())
        example = ENV_EXAMPLE.read_text(encoding="utf-8")
        for name in (
            "BRAVE_API_KEY",
            "EXA_API_KEY",
            "FIRECRAWL_API_KEY",
            "BGPT_API_KEY",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "X_AUTH_TOKEN",
            "X_CT0",
            "TGSTAT_IDR",
            "TGSTAT_SIRK",
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "TELEGRAM_SESSION",
            "TELEGRAM_SESSION_FILE",
        ):
            self.assertIn(name, example)
        self.assertTrue(AGENTS.is_file(), f"missing {AGENTS}")
        agents = AGENTS.read_text(encoding="utf-8")
        self.assertIn("skills/research-cli/SKILL.md", agents)
        self.assertIn("mcp", agents.lower())

    def test_search_routes_by_job_not_full_catalog(self) -> None:
        text = self.text.lower()
        self.assertNotIn("call every provider", text)
        self.assertNotIn("do not pick one", text)
        self.assertNotIn("same query, all of these", text)
        self.assertIn("## search", text)
        self.assertIn("one turn", text)
        self.assertIn("union of matching rows", text)
        self.assertIn("if none match, use web only", text)
        self.assertRegex(self.text, r"(?m)^\s*\| Query is about \s*\|")
        for needle in (
            "brave",
            "exa",
            "firecrawl",
            "bgpt",
            "reddit",
            "telegram",
            "sploitus",
            "exploitdb",
            "malpedia",
        ):
            self.assertIn(needle, text)

    def test_telegram_file_loop_uses_tgstat_target(self) -> None:
        self.assertIn("telegram.target", self.text)
        self.assertIn("telegram.has_media", self.text)
        examples = "\n".join(_example_lines(self.text))
        self.assertIn("--download", examples)
        self.assertIn("--media", examples)
        self.assertIn("--allow-large", examples)
        self.assertIn("telegram search", examples)
        self.assertIn("telegram get", examples)
        self.assertIn("telegram me", examples)
        self.assertIn("telegram download", examples)
        self.assertNotIn("tgstat search", examples)
        self.assertNotIn("tgstat download", examples)


if __name__ == "__main__":
    unittest.main()
