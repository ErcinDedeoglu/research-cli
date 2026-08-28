from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from research_cli import __version__  # noqa: E402
from research_cli.cli import main  # noqa: E402

from fixtures import (  # noqa: E402
    BGPT_TITLE,
    BRAVE_LLM_TEXT,
    BRAVE_URL,
    EXA_CONTENTS_TEXT,
    EXA_SEARCH_URL,
    FIRECRAWL_MAP_URL,
    FIRECRAWL_SCRAPE_MD,
    FIRECRAWL_SEARCH_URL,
    PAPER_PASSAGE,
    PAPER_TITLE,
    PAPERS_RELATED_TITLE,
    REDDIT_COMMENT_BODY,
    REDDIT_TITLE,
    SPLOITUS_TITLE,
    start_fixture_server,
)

_KEY_VARS = (
    "BGPT_API_KEY",
    "BRAVE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "RESEARCH_CLI_BASE_URL",
    "RESEARCH_CLI_NO_UPDATE",
    "RESEARCH_CLI_CACHE_DIR",
    "RESEARCH_CLI_REPO",
    "RESEARCH_CLI_GITHUB_API",
    "RESEARCH_CLI_ENV_FILE",
    "RESEARCH_CLI_NO_ENV_FILE",
)


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in _KEY_VARS:
        env.pop(name, None)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    env["RESEARCH_CLI_NO_UPDATE"] = "1"
    env["RESEARCH_CLI_NO_ENV_FILE"] = "1"
    return env


def _run_module(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "research_cli", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env or _clean_env(),
        timeout=20,
    )


class HelpTests(unittest.TestCase):
    def test_help_twice_names_five_providers(self) -> None:
        runs = [_run_module("--help") for _ in range(2)]
        for proc in runs:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(runs[0].stdout, runs[1].stdout)
        text = runs[0].stdout.lower()
        self.assertIn("bgpt", text)
        self.assertIn("brave search", text)
        self.assertIn("exa", text)
        self.assertIn("firecrawl", text)
        self.assertIn("reddit", text)
        self.assertIn("sploitus", text)
        self.assertIn("--self-update", text)

    def test_version_prints_package_version(self) -> None:
        proc = _run_module("--version")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(__version__, proc.stdout)

    def test_self_update_source_is_json(self) -> None:
        proc = _run_module("--self-update")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "unsupported")
        self.assertIn("pip install", payload["hint"])


class MissingKeyTests(unittest.TestCase):
    def test_brave_exa_firecrawl_missing_keys_name_provider(self) -> None:
        cases = [
            (["brave", "search", "q"], "brave"),
            (["exa", "search", "q"], "exa"),
            (["exa", "contents", "https://example.com"], "exa"),
            (["firecrawl", "search", "q"], "firecrawl"),
            (["firecrawl", "scrape", "https://example.com"], "firecrawl"),
            (["brave", "llm-context", "q"], "brave"),
            (["firecrawl", "map", "https://example.com"], "firecrawl"),
            (["firecrawl", "papers", "search", "q"], "firecrawl"),
            (["reddit", "search", "q"], "reddit"),
            (["reddit", "thread", "abc123"], "reddit"),
            (["reddit", "subreddit", "python"], "reddit"),
        ]
        empty = {}
        for argv, provider in cases:
            err = io.StringIO()
            code = main(argv, environ=empty, stdout=io.StringIO(), stderr=err)
            self.assertNotEqual(code, 0, argv)
            self.assertIn(provider, err.getvalue().lower())

    def test_subprocess_missing_brave_key(self) -> None:
        proc = _run_module("brave", "search", "q")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("brave", proc.stderr.lower())

    def test_subprocess_env_file_fills_brave_key(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            path.write_text("BRAVE_API_KEY=from-file\n", encoding="utf-8")
            env = _clean_env()
            env.pop("RESEARCH_CLI_NO_ENV_FILE", None)
            env.pop("BRAVE_API_KEY", None)
            env["RESEARCH_CLI_ENV_FILE"] = str(path)
            proc = _run_module("brave", "search", "q", env=env)
            self.assertNotIn("missing API key", proc.stderr.lower())
            self.assertNotEqual(proc.returncode, 2)


class FixtureServerCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server, cls.base = start_fixture_server()
        cls.env = _clean_env()
        cls.env.update(
            {
                "BRAVE_API_KEY": "fixture-brave",
                "EXA_API_KEY": "fixture-exa",
                "FIRECRAWL_API_KEY": "fixture-firecrawl",
                "REDDIT_CLIENT_ID": "fixture-reddit-id",
                "REDDIT_CLIENT_SECRET": "fixture-reddit-secret",
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return _run_module("--base-url", self.base, *args, env=self.env)

    def test_five_providers_twice_emit_fixture_fields(self) -> None:
        commands = [
            (["bgpt", "search", "CRISPR"], BGPT_TITLE),
            (["brave", "search", "rust"], BRAVE_URL),
            (["exa", "search", "llm"], EXA_SEARCH_URL),
            (["firecrawl", "search", "scraping"], FIRECRAWL_SEARCH_URL),
            (["reddit", "search", "python"], REDDIT_TITLE),
            (["sploitus", "search", "log4j"], SPLOITUS_TITLE),
        ]
        for _ in range(2):
            for args, needle in commands:
                proc = self._cli(*args)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(needle, proc.stdout)

    def test_base_url_after_subcommand(self) -> None:
        proc = _run_module(
            "bgpt",
            "search",
            "CRISPR",
            "--base-url",
            self.base,
            "--timeout",
            "15",
            env=self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(BGPT_TITLE, proc.stdout)

    def test_exa_contents_and_firecrawl_scrape(self) -> None:
        contents = self._cli("exa", "contents", "https://exa.example/page")
        self.assertEqual(contents.returncode, 0, contents.stderr)
        self.assertIn(EXA_CONTENTS_TEXT, contents.stdout)
        scrape = self._cli("firecrawl", "scrape", "https://firecrawl.example/page", "--live")
        self.assertEqual(scrape.returncode, 0, scrape.stderr)
        self.assertIn(FIRECRAWL_SCRAPE_MD, scrape.stdout)

    def test_new_research_commands(self) -> None:
        cases = [
            (["brave", "llm-context", "RAG"], BRAVE_LLM_TEXT),
            (["firecrawl", "map", "https://docs.firecrawl.dev", "--search", "webhook"], FIRECRAWL_MAP_URL),
            (["firecrawl", "papers", "search", "diffusion"], PAPER_TITLE),
            (["firecrawl", "papers", "inspect", "arxiv:2105.05233"], PAPER_TITLE),
            (
                ["firecrawl", "papers", "read", "arxiv:2105.05233", "--question", "architecture"],
                PAPER_PASSAGE,
            ),
            (
                ["firecrawl", "papers", "related", "arxiv:2105.05233", "--intent", "attention"],
                PAPERS_RELATED_TITLE,
            ),
            (["reddit", "thread", "abc123", "--sort", "top"], REDDIT_COMMENT_BODY),
            (["reddit", "subreddit", "python", "--sort", "top", "--time", "week"], REDDIT_TITLE),
            (["sploitus", "search", "log4j", "--sort", "score", "--type", "exploits"], SPLOITUS_TITLE),
            (["sploitus", "exploit", "EDB-ID:50592"], SPLOITUS_TITLE),
            (["sploitus", "cve", "CVE-2021-44228"], "Fixture CVE description"),
            (["sploitus", "product", "wordpress"], "CVE-2026-60137"),
            (["sploitus", "latest"], "Fixture latest exploit"),
            (["sploitus", "autocomplete", "log4"], "log4j"),
        ]
        for args, needle in cases:
            proc = self._cli(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr + str(args))
            self.assertIn(needle, proc.stdout)


if __name__ == "__main__":
    unittest.main()
