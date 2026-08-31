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
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(SRC))

from research_cli import __version__  # noqa: E402
from research_cli.cli import _csv, _dispatch, _origin, main, run  # noqa: E402
from research_cli.errors import UpdateError  # noqa: E402

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
    EDB_PAPER_TITLE,
    EDB_SHELLCODE_TITLE,
    EDB_SOURCE,
    EDB_TITLE,
    MALPEDIA_FAMILY_ID,
    MALPEDIA_REF_URL,
    MALPEDIA_YARA_NAME,
    MALPEDIA_YARA_RAW,
    MALPEDIA_ZIP,
    X_CURSOR,
    X_ONDEMAND_HASH,
    X_TEXT,
    X_TWEET_ID,
    X_USER,
    TGSTAT_TEXT,
    snapshot_path_counts,
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
    "X_AUTH_TOKEN",
    "X_CT0",
    "TGSTAT_IDR",
    "TGSTAT_SIRK",
    "TGSTAT_CSRK",
    "TGSTAT_SETTINGS",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION",
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
        self.assertIn("exploitdb", text)
        self.assertIn("malpedia", text)
        self.assertIn("twitter", text)
        self.assertIn("telegram", text)
        self.assertIn("tgstat", text)
        self.assertIn("--self-update", text)

    def test_version_prints_package_version(self) -> None:
        proc = _run_module("--version")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(__version__, proc.stdout)

    def test_help_topics_inprocess_and_run_module(self) -> None:
        environ = {"RESEARCH_CLI_NO_UPDATE": "1"}
        listed = io.StringIO()
        self.assertEqual(
            main(["help"], environ=environ, stdout=listed, spawn_update=lambda _e: None),
            0,
        )
        self.assertIn("install", json.loads(listed.getvalue())["topics"])
        install = io.StringIO()
        self.assertEqual(
            main(
                ["help", "installation"],
                environ=environ,
                stdout=install,
                spawn_update=lambda _e: None,
            ),
            0,
        )
        self.assertEqual(json.loads(install.getvalue())["topic"], "install")
        keys = io.StringIO()
        self.assertEqual(
            main(["help", "keys"], environ=environ, stdout=keys, spawn_update=lambda _e: None),
            0,
        )
        self.assertEqual(json.loads(keys.getvalue())["topic"], "keys")
        err = io.StringIO()
        self.assertEqual(
            main(
                ["help", "nope"],
                environ=environ,
                stdout=io.StringIO(),
                stderr=err,
                spawn_update=lambda _e: None,
            ),
            1,
        )
        self.assertIn("install", err.getvalue().lower())

    def test_run_and_cli_dunder_main_exit(self) -> None:
        from unittest.mock import patch
        import runpy

        with patch("research_cli.cli.main", return_value=4):
            with self.assertRaises(SystemExit) as ctx:
                run()
            self.assertEqual(ctx.exception.code, 4)
        with patch("research_cli.cli.main", return_value=0), patch.object(
            sys, "argv", ["research-cli"]
        ):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("research_cli", run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
        with patch("research_cli.cli.main", return_value=0), patch.object(
            sys, "argv", ["research-cli"]
        ):
            with self.assertRaises(SystemExit):
                runpy.run_module("research_cli.cli", run_name="__main__")

    def test_self_update_error_and_flush_failure(self) -> None:
        from unittest.mock import patch

        err = io.StringIO()

        def boom(**_kwargs):
            raise UpdateError("nope")

        with patch("research_cli.cli.run_self_update", boom):
            code = main(
                ["--self-update"],
                environ={"RESEARCH_CLI_NO_UPDATE": "1"},
                stdout=io.StringIO(),
                stderr=err,
                spawn_update=lambda _e: None,
            )
        self.assertEqual(code, 1)
        self.assertIn("nope", err.getvalue())

        class Broken(io.StringIO):
            def flush(self) -> None:
                raise OSError("flush-fail")

        code = main(
            ["help"],
            environ={"RESEARCH_CLI_NO_UPDATE": "1"},
            stdout=Broken(),
            spawn_update=lambda _e: None,
        )
        self.assertEqual(code, 0)

    def test_csv_origin_and_unknown_dispatch(self) -> None:
        import argparse

        self.assertIsNone(_csv(None))
        self.assertIsNone(_csv(" , , "))
        self.assertEqual(_csv("a, b"), ["a", "b"])
        args = argparse.Namespace()
        self.assertEqual(
            _origin(args, {"RESEARCH_CLI_BASE_URL": "http://fixture"}, "https://x.com"),
            "http://fixture",
        )
        self.assertEqual(_origin(args, {}, "https://x.com"), "https://x.com")
        with self.assertRaises(ValueError):
            _dispatch(argparse.Namespace(provider="nope"), {}, None)
        with self.assertRaises(ValueError):
            _dispatch(argparse.Namespace(provider="x", operation="likes"), {"X_AUTH_TOKEN": "a", "X_CT0": "b"}, None)

    def test_self_update_source_is_json(self) -> None:
        proc = _run_module("--self-update")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "unsupported")
        self.assertIn("pip install", payload["hint"])

    def test_help_install_prints_release_assets(self) -> None:
        listed = _run_module("help")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        index = json.loads(listed.stdout)
        self.assertEqual(index["provider"], "help")
        self.assertIn("install", index["topics"])
        self.assertIn("install", index["hint"])
        proc = _run_module("help", "install")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["provider"], "help")
        self.assertEqual(payload["topic"], "install")
        self.assertIn("INSTALL.md", payload.get("url", ""))
        body = payload["body"]
        self.assertIn("releases/latest/download", body)
        self.assertIn("command -v research-cli", body)
        self.assertIn("research-cli-Darwin-arm64", body)
        self.assertIn("research-cli-Linux-x86_64", body)
        self.assertIn("research-cli-Linux-aarch64", body)
        self.assertIn("research-cli-Windows-x86_64.exe", body)
        self.assertIn("research-cli.pyz", body)
        alias = _run_module("help", "installation")
        self.assertEqual(alias.returncode, 0, alias.stderr)
        self.assertEqual(json.loads(alias.stdout)["body"], body)
        bad = _run_module("help", "nope")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("install", bad.stderr.lower())

    def test_help_keys_prints_env_key_table(self) -> None:
        listed = _run_module("help")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("keys", json.loads(listed.stdout)["topics"])
        proc = _run_module("help", "keys")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["provider"], "help")
        self.assertEqual(payload["topic"], "keys")
        body = payload["body"]
        self.assertIn(".config/research-cli/env", body)
        for name in (
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
        ):
            self.assertIn(name, body)


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
            (["x", "search", "q"], "x"),
            (["x", "thread", "123"], "x"),
            (["tgstat", "search", "q"], "tgstat"),
            (["tgstat", "me"], "tgstat"),
            (["tgstat", "sources", "q"], "tgstat"),
            (["tgstat", "mentions", "q"], "tgstat"),
            (["tgstat", "export", "q"], "tgstat"),
            (["tgstat", "download", "https://t.me/durov/1"], "telegram"),
            (["telegram", "get", "https://t.me/durov/1"], "telegram"),
            (["telegram", "me"], "telegram"),
            (["telegram", "login", "--phone", "+1"], "telegram"),
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

    def test_subprocess_missing_x_keys(self) -> None:
        search = _run_module("x", "search", "q")
        self.assertEqual(search.returncode, 2, search.stderr)
        self.assertIn("x", search.stderr.lower())
        self.assertIn("x_auth_token", search.stderr.lower())
        thread = _run_module("x", "thread", "123")
        self.assertEqual(thread.returncode, 2, thread.stderr)
        self.assertIn("x_ct0", thread.stderr.lower())

    def test_subprocess_missing_tgstat_cookies(self) -> None:
        search = _run_module("tgstat", "search", "q")
        self.assertEqual(search.returncode, 2, search.stderr)
        self.assertIn("tgstat", search.stderr.lower())
        self.assertIn("tgstat_idr", search.stderr.lower())
        catalogs = _run_module("tgstat", "catalogs")
        self.assertEqual(catalogs.returncode, 0, catalogs.stderr)
        self.assertIn("english", catalogs.stdout)

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
        cls._cache = tempfile.TemporaryDirectory()
        cls.env = _clean_env()
        cls.env.update(
            {
                "BRAVE_API_KEY": "fixture-brave",
                "EXA_API_KEY": "fixture-exa",
                "FIRECRAWL_API_KEY": "fixture-firecrawl",
                "REDDIT_CLIENT_ID": "fixture-reddit-id",
                "REDDIT_CLIENT_SECRET": "fixture-reddit-secret",
                "X_AUTH_TOKEN": "fixture-x-auth",
                "X_CT0": "fixture-x-ct0",
                "TGSTAT_IDR": "fixture-idr",
                "TGSTAT_SIRK": "fixture-sirk",
                "RESEARCH_CLI_CACHE_DIR": cls._cache.name,
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._cache.cleanup()

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
            (["exploitdb", "search", "log4j"], EDB_TITLE),
            (["malpedia", "search", "emotet"], MALPEDIA_FAMILY_ID),
            (["x", "search", "VMProtect"], X_TEXT),
            (["tgstat", "search", "llvm"], TGSTAT_TEXT),
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
            (["sploitus", "home"], "CVE-2025-55182"),
            (["exploitdb", "search", "log4j", "--type", "remote", "--platform", "java"], EDB_TITLE),
            (["exploitdb", "latest"], EDB_TITLE),
            (["exploitdb", "exploit", "50592"], EDB_TITLE),
            (["exploitdb", "raw", "50592"], EDB_SOURCE.splitlines()[0]),
            (["exploitdb", "papers", "polkit"], EDB_PAPER_TITLE),
            (["exploitdb", "paper", "50981"], EDB_PAPER_TITLE),
            (["exploitdb", "shellcodes", "calc"], EDB_SHELLCODE_TITLE),
            (["exploitdb", "shellcode", "52599"], EDB_SHELLCODE_TITLE),
            (["exploitdb", "ghdb", "ganglia"], "Ganglia"),
            (["exploitdb", "dork", "2"], "Ganglia Cluster Reports"),
            (["exploitdb", "authors", "leon"], "leonjza"),
            (["exploitdb", "stats"], "46664"),
            (["malpedia", "search", "emotet"], MALPEDIA_FAMILY_ID),
            (["malpedia", "family", "win.emotet"], "Emotet"),
            (["malpedia", "actor", "apt28"], "APT28"),
            (["malpedia", "yara", "win.emotet"], MALPEDIA_YARA_NAME),
            (["malpedia", "families", "--limit", "2"], MALPEDIA_FAMILY_ID),
            (["malpedia", "families", "--full"], "Emotet"),
            (["malpedia", "actors", "--limit", "2"], "apt28"),
            (["malpedia", "actors", "--full"], "APT28"),
            (["malpedia", "bib", "--family", "win.emotet"], "kupreev:20250410:goffee:adb0ca3"),
            (["malpedia", "misp"], "Malpedia"),
            (["malpedia", "references", "--url", MALPEDIA_REF_URL], "GOFFEE"),
            (["malpedia", "yara-list", "--family", "win.emotet"], MALPEDIA_YARA_NAME),
            (["malpedia", "yara-after", "2026-01-01"], MALPEDIA_YARA_NAME),
            (["malpedia", "version"], "26109"),
            (["x", "search", "VMProtect LLVM", "--product", "latest"], X_TEXT),
            (["x", "search", "q", "--product", "top", "--count", "5"], X_TEXT),
            (["x", "search", "q", "--product", "people"], X_TEXT),
            (["x", "search", "q", "--product", "media", "--cursor", X_CURSOR], X_TEXT),
            (["x", "thread", X_TWEET_ID], X_TEXT),
            (
                ["x", "thread", f"https://x.com/{X_USER}/status/{X_TWEET_ID}"],
                X_TEXT,
            ),
            (
                ["x", "thread", f"https://twitter.com/{X_USER}/status/{X_TWEET_ID}"],
                X_TEXT,
            ),
        ]
        for args, needle in cases:
            proc = self._cli(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr + str(args))
            self.assertIn(needle, proc.stdout)

    def test_inprocess_dispatch_covers_cli_branches(self) -> None:
        environ = dict(self.env)
        environ["RESEARCH_CLI_BASE_URL"] = self.base
        environ["RESEARCH_CLI_NO_UPDATE"] = "1"
        extra = [
            (["bgpt", "search", "CRISPR", "--days-back", "7", "--num-results", "3"], BGPT_TITLE),
            (["brave", "search", "rust", "--country", "US", "--offset", "0"], BRAVE_URL),
            (["brave", "llm-context", "RAG"], BRAVE_LLM_TEXT),
            (
                [
                    "exa",
                    "search",
                    "llm",
                    "--include-domains",
                    "arxiv.org",
                    "--exclude-domains",
                    "spam.example",
                    "--category",
                    "research paper",
                    "--start-published",
                    "2020-01-01",
                    "--end-published",
                    "2026-01-01",
                    "--highlights",
                    "--text",
                ],
                EXA_SEARCH_URL,
            ),
            (["exa", "contents", "https://exa.example/page"], EXA_CONTENTS_TEXT),
            (
                [
                    "firecrawl",
                    "scrape",
                    "https://firecrawl.example/page",
                    "--live",
                    "--no-main-content",
                    "--formats",
                    "markdown",
                    "--max-age",
                    "0",
                ],
                FIRECRAWL_SCRAPE_MD,
            ),
            (
                [
                    "firecrawl",
                    "search",
                    "scraping",
                    "--categories",
                    "research",
                    "--include-domains",
                    "example.com",
                    "--scrape",
                ],
                FIRECRAWL_SEARCH_URL,
            ),
            (["firecrawl", "map", "https://docs.firecrawl.dev", "--search", "webhook"], FIRECRAWL_MAP_URL),
            (
                [
                    "firecrawl",
                    "papers",
                    "search",
                    "diffusion",
                    "--k",
                    "5",
                    "--from",
                    "2020-01-01",
                    "--to",
                    "2026-01-01",
                ],
                PAPER_TITLE,
            ),
            (["firecrawl", "papers", "inspect", "arxiv:2105.05233"], PAPER_TITLE),
            (
                ["firecrawl", "papers", "read", "arxiv:2105.05233", "--question", "architecture"],
                PAPER_PASSAGE,
            ),
            (
                [
                    "firecrawl",
                    "papers",
                    "related",
                    "arxiv:2105.05233",
                    "--intent",
                    "attention",
                    "--anchors",
                    "a,b",
                ],
                PAPERS_RELATED_TITLE,
            ),
            (["reddit", "search", "python", "--subreddit", "python"], REDDIT_TITLE),
            (["reddit", "thread", "abc123", "--depth", "2"], REDDIT_COMMENT_BODY),
            (["reddit", "subreddit", "python"], REDDIT_TITLE),
            (["sploitus", "search", "log4j", "--source", "--type", "tools"], SPLOITUS_TITLE),
            (["sploitus", "exploit", "EDB-ID:50592"], SPLOITUS_TITLE),
            (["sploitus", "cve", "CVE-2021-44228"], "Fixture CVE description"),
            (["sploitus", "product", "wordpress"], "CVE-2026-60137"),
            (["sploitus", "latest"], "Fixture latest exploit"),
            (["sploitus", "home"], "CVE-2025-55182"),
            (["sploitus", "autocomplete", "log4"], "log4j"),
            (
                [
                    "exploitdb",
                    "search",
                    "log4j",
                    "--type",
                    "remote",
                    "--verified",
                    "--hasapp",
                    "--nomsf",
                    "--cve",
                    "CVE-2021-44228",
                    "--tag",
                    "sqli",
                    "--text",
                    "payload",
                    "--author",
                    "1",
                ],
                EDB_TITLE,
            ),
            (["exploitdb", "latest"], EDB_TITLE),
            (["exploitdb", "exploit", "50592"], EDB_TITLE),
            (["exploitdb", "raw", "50592"], EDB_SOURCE.splitlines()[0]),
            (["exploitdb", "papers", "polkit", "--language", "english"], EDB_PAPER_TITLE),
            (["exploitdb", "paper", "50981"], EDB_PAPER_TITLE),
            (["exploitdb", "shellcodes", "calc"], EDB_SHELLCODE_TITLE),
            (["exploitdb", "shellcode", "52599"], EDB_SHELLCODE_TITLE),
            (["exploitdb", "ghdb", "ganglia", "--category", "Files Containing Passwords"], "Ganglia"),
            (["exploitdb", "dork", "2"], "Ganglia Cluster Reports"),
            (["exploitdb", "authors", "leon"], "leonjza"),
            (["exploitdb", "stats"], "46664"),
            (["malpedia", "search", "emotet"], MALPEDIA_FAMILY_ID),
            (["malpedia", "family", "win.emotet"], "Emotet"),
            (["malpedia", "actor", "apt28"], "APT28"),
            (["malpedia", "yara", "win.emotet"], MALPEDIA_YARA_NAME),
            (["malpedia", "families", "--full", "--limit", "2"], "Emotet"),
            (["malpedia", "actors", "--full"], "APT28"),
            (["malpedia", "bib", "--actor", "goffee"], "kupreev"),
            (["malpedia", "misp"], "Malpedia"),
            (["malpedia", "references", "--url", MALPEDIA_REF_URL], "GOFFEE"),
            (["malpedia", "yara-list", "--family", "win.emotet"], MALPEDIA_YARA_NAME),
            (["malpedia", "yara-after", "2026-01-01"], MALPEDIA_YARA_NAME),
            (["malpedia", "version"], "26109"),
            (["x", "search", "q", "--compact", "--fields", "id,url,text"], X_TEXT),
            (["x", "thread", X_TWEET_ID], X_TEXT),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            extra.append((["exploitdb", "download", "50592", "--output", tmp], "50592"))
            extra.append((["malpedia", "yara", "win.emotet", "--zip", "--output", tmp], "path"))
            extra.append((["malpedia", "yara-dump", "--tlp", "white", "--output", tmp], "path"))
            extra.append((["malpedia", "yara-dump", "--auto", "--zip", "--output", tmp], "path"))
            extra.append((["malpedia", "families", "--output", tmp], "path"))
            extra.append((["malpedia", "bib", "--family", "win.emotet", "--output", tmp], "path"))
            for args, needle in extra:
                out, err = io.StringIO(), io.StringIO()
                code = main(
                    list(args),
                    environ=environ,
                    stdout=out,
                    stderr=err,
                    spawn_update=lambda _e: None,
                )
                self.assertEqual(code, 0, err.getvalue() + str(args))
                self.assertIn(needle, out.getvalue())

    def test_x_help_and_invalid_product(self) -> None:
        help_proc = self._cli("x", "--help")
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("search", help_proc.stdout.lower())
        self.assertIn("thread", help_proc.stdout.lower())
        search_help = self._cli("x", "search", "--help")
        self.assertEqual(search_help.returncode, 0, search_help.stderr)
        self.assertIn("--product", search_help.stdout)
        self.assertIn("--count", search_help.stdout)
        self.assertIn("--cursor", search_help.stdout)
        self.assertIn("--compact", search_help.stdout)
        self.assertIn("--fields", search_help.stdout)
        thread_help = self._cli("x", "thread", "--help")
        self.assertEqual(thread_help.returncode, 0, thread_help.stderr)
        self.assertIn("--cursor", thread_help.stdout)
        bad = self._cli("x", "search", "q", "--product", "hot")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("product", (bad.stderr + bad.stdout).lower())
        compact = self._cli(
            "x",
            "search",
            "q",
            "--compact",
            "--fields",
            "id,url,text",
        )
        self.assertEqual(compact.returncode, 0, compact.stderr)
        payload = json.loads(compact.stdout)
        self.assertEqual(payload["provider"], "x")
        self.assertEqual(set(payload["results"][0]), {"id", "url", "text"})
        self.assertEqual(payload["results"][0]["text"], X_TEXT)
        self.assertEqual(compact.stdout.count("\n"), 1)

    def test_x_expired_cookies_exit_2(self) -> None:
        def send_401(_request):
            from research_cli.http import HttpResponse

            return HttpResponse(401, {}, b'{"errors":[{"message":"unauthorized"}]}')

        err = io.StringIO()
        code = main(
            ["x", "search", "q"],
            environ={
                "X_AUTH_TOKEN": "dead",
                "X_CT0": "dead",
                "RESEARCH_CLI_NO_UPDATE": "1",
            },
            transport=send_401,
            stdout=io.StringIO(),
            stderr=err,
            spawn_update=lambda _e: None,
        )
        self.assertEqual(code, 2)
        self.assertIn("x", err.getvalue().lower())
        self.assertIn("cookie", err.getvalue().lower())
        self.assertIn("expired", err.getvalue().lower())

    def test_x_cli_second_process_skips_bootstrap_http(self) -> None:
        server, base = start_fixture_server()
        try:
            with tempfile.TemporaryDirectory() as raw:
                env = _clean_env()
                env.update(
                    {
                        "X_AUTH_TOKEN": "fixture-x-auth",
                        "X_CT0": "fixture-x-ct0",
                        "RESEARCH_CLI_CACHE_DIR": raw,
                    }
                )
                first = _run_module("--base-url", base, "x", "search", "q", env=env)
                self.assertEqual(first.returncode, 0, first.stderr)
                payload = json.loads(first.stdout)
                self.assertEqual(payload["provider"], "x")
                self.assertIn(X_TEXT, first.stdout)
                after_first = snapshot_path_counts(server)
                second = _run_module("--base-url", base, "x", "search", "q", env=env)
                self.assertEqual(second.returncode, 0, second.stderr)
                after_second = snapshot_path_counts(server)
                ondemand = f"/responsive-web/client-web/ondemand.s.{X_ONDEMAND_HASH}a.js"
                self.assertEqual(after_first.get("/home"), 1)
                self.assertEqual(after_second.get("/home"), 1)
                self.assertEqual(after_first.get(ondemand), 1)
                self.assertEqual(after_second.get(ondemand), 1)
                self.assertEqual(after_first.get("/responsive-web/client-web/main.fixturea.js"), 1)
                self.assertEqual(
                    after_second.get("/responsive-web/client-web/main.fixturea.js"), 1
                )
                gql_first = sum(
                    n for p, n in after_first.items() if p.endswith("/SearchTimeline")
                )
                gql_second = sum(
                    n for p, n in after_second.items() if p.endswith("/SearchTimeline")
                )
                self.assertEqual(gql_first, 1)
                self.assertEqual(gql_second, 2)
        finally:
            server.shutdown()
            server.server_close()

    def test_exploitdb_download_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._cli("exploitdb", "download", "50592", "--output", tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            path = Path(payload["path"])
            self.assertEqual(payload["filename"], "50592.py")
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), EDB_SOURCE)

    def test_malpedia_yara_dump_and_zip_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = self._cli(
                "malpedia", "yara-dump", "--tlp", "white", "--output", tmp
            )
            self.assertEqual(dump.returncode, 0, dump.stderr)
            payload = json.loads(dump.stdout)
            path = Path(payload["path"])
            self.assertEqual(payload["filename"], "malpedia_tlp_white.yar")
            self.assertEqual(path.read_text(encoding="utf-8"), MALPEDIA_YARA_RAW)
            zipped = self._cli(
                "malpedia", "yara", "win.emotet", "--zip", "--output", tmp
            )
            self.assertEqual(zipped.returncode, 0, zipped.stderr)
            zip_payload = json.loads(zipped.stdout)
            self.assertEqual(Path(zip_payload["path"]).read_bytes(), MALPEDIA_ZIP)


if __name__ == "__main__":
    unittest.main()
