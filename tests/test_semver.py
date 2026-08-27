from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import semver  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


class BumpTests(unittest.TestCase):
    def test_parse_and_format(self) -> None:
        self.assertEqual(semver.parse_semver("v1.2.3"), (1, 2, 3))
        self.assertEqual(semver.format_semver((0, 1, 0)), "0.1.0")
        with self.assertRaises(ValueError):
            semver.parse_semver("r-abc1234")

    def test_bump_levels(self) -> None:
        self.assertEqual(semver.bump_version("0.1.0", "patch"), "0.1.1")
        self.assertEqual(semver.bump_version("0.1.4", "minor"), "0.2.0")
        self.assertEqual(semver.bump_version("0.2.1", "major"), "0.3.0")
        self.assertEqual(semver.bump_version("1.4.2", "major"), "2.0.0")
        self.assertEqual(semver.bump_version("1.4.2", "minor"), "1.5.0")

    def test_conventional_commit_levels(self) -> None:
        self.assertEqual(semver.commit_bump_level("fix: timeout"), "patch")
        self.assertEqual(semver.commit_bump_level("chore: cache pip"), "patch")
        self.assertEqual(semver.commit_bump_level("feat: add map"), "minor")
        self.assertEqual(semver.commit_bump_level("feat(cli): add map"), "minor")
        self.assertEqual(semver.commit_bump_level("feat!: drop flag"), "major")
        self.assertEqual(
            semver.commit_bump_level("fix: x\n\nBREAKING CHANGE: gone"),
            "major",
        )
        self.assertEqual(semver.commit_bump_level("not conventional"), "patch")

    def test_max_level(self) -> None:
        self.assertEqual(
            semver.max_bump_level(["chore: a", "feat: b", "fix: c"]),
            "minor",
        )
        self.assertEqual(
            semver.max_bump_level(["feat: b", "feat!: c"]),
            "major",
        )


class VersionFileTests(unittest.TestCase):
    def test_read_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "__init__.py"
            path.write_text('"""pkg"""\n\n__version__ = "0.1.0"\n', encoding="utf-8")
            self.assertEqual(semver.read_version_file(path), "0.1.0")
            semver.apply_version("0.2.0", path)
            self.assertEqual(semver.read_version_file(path), "0.2.0")
            self.assertIn('__version__ = "0.2.0"', path.read_text(encoding="utf-8"))

    def test_apply_skill_version_replaces_or_inserts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "SKILL.md"
            path.write_text(
                "---\nname: research-cli\ndescription: x\n---\n\n# research-cli\n",
                encoding="utf-8",
            )
            semver.apply_skill_version("0.2.0", path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("version: 0.2.0", text)
            semver.apply_skill_version("0.3.1", path)
            self.assertIn("version: 0.3.1", path.read_text(encoding="utf-8"))
            self.assertNotIn("version: 0.2.0", path.read_text(encoding="utf-8"))


class GitNextVersionTests(unittest.TestCase):
    def _repo(self) -> tempfile.TemporaryDirectory[str]:
        tmp = tempfile.TemporaryDirectory()
        cwd = Path(tmp.name)
        _git(cwd, "init", "-b", "main")
        _git(cwd, "config", "user.email", "semver@example.com")
        _git(cwd, "config", "user.name", "semver")
        (cwd / "f.txt").write_text("a\n", encoding="utf-8")
        _git(cwd, "add", "f.txt")
        _git(cwd, "commit", "-m", "chore: start")
        return tmp

    def test_no_tag_uses_head_message_and_file_version(self) -> None:
        tmp = self._repo()
        cwd = Path(tmp.name)
        try:
            _git(cwd, "commit", "--allow-empty", "-m", "feat: add papers")
            got = semver.next_version(cwd=cwd, current="0.1.0")
            self.assertEqual(got, "0.2.0")
        finally:
            tmp.cleanup()

    def test_commits_since_tag(self) -> None:
        tmp = self._repo()
        cwd = Path(tmp.name)
        try:
            _git(cwd, "tag", "v0.2.0")
            _git(cwd, "commit", "--allow-empty", "-m", "fix: handle 404")
            _git(cwd, "commit", "--allow-empty", "-m", "docs: readme")
            got = semver.next_version(cwd=cwd, current="0.2.0")
            self.assertEqual(got, "0.2.1")
        finally:
            tmp.cleanup()

    def test_already_on_tag_does_not_bump(self) -> None:
        tmp = self._repo()
        cwd = Path(tmp.name)
        try:
            _git(cwd, "tag", "v0.3.0")
            got = semver.next_version(cwd=cwd, current="0.3.0")
            self.assertEqual(got, "0.3.0")
        finally:
            tmp.cleanup()

    def test_ignores_non_semver_tags(self) -> None:
        tmp = self._repo()
        cwd = Path(tmp.name)
        try:
            _git(cwd, "tag", "r-abc1234")
            _git(cwd, "commit", "--allow-empty", "-m", "fix: n")
            got = semver.next_version(cwd=cwd, current="0.1.0")
            self.assertEqual(got, "0.1.1")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
