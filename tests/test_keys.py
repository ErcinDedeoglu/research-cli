from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.keys import (  # noqa: E402
    default_env_path,
    load_provider_keys,
    parse_env_file,
)


class EnvFileTests(unittest.TestCase):
    def test_parse_skips_comments_and_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            path.write_text(
                "# comment\n"
                "BRAVE_API_KEY=abc\n"
                "export EXA_API_KEY=\"xyz\"\n"
                "FIRECRAWL_API_KEY='fc-1'\n"
                "\n",
                encoding="utf-8",
            )
            parsed = parse_env_file(path)
            self.assertEqual(parsed["BRAVE_API_KEY"], "abc")
            self.assertEqual(parsed["EXA_API_KEY"], "xyz")
            self.assertEqual(parsed["FIRECRAWL_API_KEY"], "fc-1")

    def test_load_fills_blanks_env_wins(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            path.write_text(
                "BRAVE_API_KEY=fromfile\nEXA_API_KEY=file-exa\n",
                encoding="utf-8",
            )
            out = load_provider_keys(
                {
                    "RESEARCH_CLI_ENV_FILE": str(path),
                    "EXA_API_KEY": "fromenv",
                }
            )
            self.assertEqual(out["BRAVE_API_KEY"], "fromfile")
            self.assertEqual(out["EXA_API_KEY"], "fromenv")

    def test_no_env_file_skips_disk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            path.write_text("BRAVE_API_KEY=secret\n", encoding="utf-8")
            out = load_provider_keys(
                {
                    "RESEARCH_CLI_ENV_FILE": str(path),
                    "RESEARCH_CLI_NO_ENV_FILE": "1",
                }
            )
            self.assertNotIn("BRAVE_API_KEY", out)

    def test_missing_file_is_empty(self) -> None:
        out = load_provider_keys(
            {"RESEARCH_CLI_ENV_FILE": "/no/such/research-cli-env"}
        )
        self.assertEqual(out.get("BRAVE_API_KEY", ""), "")

    def test_default_unix_path(self) -> None:
        path = default_env_path({"XDG_CONFIG_HOME": "/tmp/xdg"})
        self.assertEqual(path, Path("/tmp/xdg/research-cli/env"))


if __name__ == "__main__":
    unittest.main()
