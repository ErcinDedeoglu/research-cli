from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from research_cli.cli import main  # noqa: E402

from fixtures import (  # noqa: E402
    BGPT_TITLE,
    BRAVE_URL,
    EXA_CONTENTS_TEXT,
    EXA_SEARCH_URL,
    FIRECRAWL_SCRAPE_MD,
    FIRECRAWL_SEARCH_URL,
    start_fixture_server,
)

_KEY_VARS = (
    "BGPT_API_KEY",
    "BRAVE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "RESEARCH_CLI_BASE_URL",
)


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in _KEY_VARS:
        env.pop(name, None)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
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
    def test_help_twice_names_four_providers(self) -> None:
        runs = [_run_module("--help") for _ in range(2)]
        for proc in runs:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(runs[0].stdout, runs[1].stdout)
        text = runs[0].stdout.lower()
        self.assertIn("bgpt", text)
        self.assertIn("brave search", text)
        self.assertIn("exa", text)
        self.assertIn("firecrawl", text)


class MissingKeyTests(unittest.TestCase):
    def test_brave_exa_firecrawl_missing_keys_name_provider(self) -> None:
        cases = [
            (["brave", "search", "q"], "brave"),
            (["exa", "search", "q"], "exa"),
            (["exa", "contents", "https://example.com"], "exa"),
            (["firecrawl", "search", "q"], "firecrawl"),
            (["firecrawl", "scrape", "https://example.com"], "firecrawl"),
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
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return _run_module("--base-url", self.base, *args, env=self.env)

    def test_four_providers_twice_emit_fixture_fields(self) -> None:
        commands = [
            (["bgpt", "search", "CRISPR"], BGPT_TITLE),
            (["brave", "search", "rust"], BRAVE_URL),
            (["exa", "search", "llm"], EXA_SEARCH_URL),
            (["firecrawl", "search", "scraping"], FIRECRAWL_SEARCH_URL),
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
        scrape = self._cli("firecrawl", "scrape", "https://firecrawl.example/page")
        self.assertEqual(scrape.returncode, 0, scrape.stderr)
        self.assertIn(FIRECRAWL_SCRAPE_MD, scrape.stdout)


if __name__ == "__main__":
    unittest.main()
