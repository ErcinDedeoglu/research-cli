#!/usr/bin/env python3
"""SemVer helper for research-cli.

Reads the current version from src/research_cli/__init__.py, computes the next
version from git tags (vMAJOR.MINOR.PATCH) and conventional commit messages,
and can write the result back.

Bump rules (highest wins across commits since the last v* tag):
  feat:                     minor
  fix:/chore:/docs:/other:  patch
  type!: or BREAKING CHANGE major (on 0.x, major is treated as minor)

With no v* tag yet, only HEAD is inspected and the file version is the base.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "research_cli" / "__init__.py"
_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"', re.M)
_SUBJECT_RE = re.compile(r"^(\w+)(?:\([^)]*\))?(!)?:\s*")
_RANK = {"patch": 0, "minor": 1, "major": 2}


def parse_semver(value: str) -> tuple[int, int, int]:
    text = value.strip()
    if text[:1] in {"v", "V"}:
        text = text[1:]
    parts = text.split(".")
    if len(parts) < 3:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {value}")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {value}") from exc
    return major, minor, patch


def format_semver(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def bump_version(version: str, level: str) -> str:
    major, minor, patch = parse_semver(version)
    if level == "major":
        if major == 0:
            return format_semver((0, minor + 1, 0))
        return format_semver((major + 1, 0, 0))
    if level == "minor":
        return format_semver((major, minor + 1, 0))
    if level == "patch":
        return format_semver((major, minor, patch + 1))
    raise ValueError(f"unknown bump level: {level}")


def commit_bump_level(message: str) -> str:
    if re.search(r"(?im)^breaking change:", message):
        return "major"
    subject = ""
    for line in message.splitlines():
        if line.strip():
            subject = line.strip()
            break
    match = _SUBJECT_RE.match(subject)
    if not match:
        return "patch"
    kind, bang = match.group(1).lower(), match.group(2)
    if bang:
        return "major"
    if kind == "feat":
        return "minor"
    return "patch"


def max_bump_level(messages: list[str]) -> str:
    best = "patch"
    for message in messages:
        level = commit_bump_level(message)
        if _RANK[level] > _RANK[best]:
            best = level
    return best


def read_version_file(path: Path = INIT) -> str:
    match = _VERSION_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"no __version__ in {path}")
    return match.group(1)


def apply_version(version: str, path: Path = INIT) -> None:
    parse_semver(version)
    text = path.read_text(encoding="utf-8")
    updated, count = _VERSION_RE.subn(f'__version__ = "{version}"', text, count=1)
    if count != 1:
        raise ValueError(f"could not replace __version__ in {path}")
    path.write_text(updated, encoding="utf-8")


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git failed")
    return proc.stdout


def latest_v_tag(cwd: Path) -> str | None:
    output = _git(["tag", "-l", "v[0-9]*", "--sort=-v:refname"], cwd)
    for raw in output.splitlines():
        tag = raw.strip()
        if not tag:
            continue
        try:
            parse_semver(tag)
        except ValueError:
            continue
        return tag
    return None


def commit_messages_since(cwd: Path, tag: str | None) -> list[str]:
    args = ["log", "--format=%B%x1e"]
    if tag:
        args.append(f"{tag}..HEAD")
    else:
        args.append("-1")
    output = _git(args, cwd)
    return [item.strip() for item in output.split("\x1e") if item.strip()]


def next_version(*, cwd: Path = ROOT, current: str | None = None) -> str:
    if current is None:
        current = read_version_file(INIT)
    tag = latest_v_tag(cwd)
    messages = commit_messages_since(cwd, tag)
    if tag is not None:
        base = format_semver(parse_semver(tag))
        if not messages:
            return base
        return bump_version(base, max_bump_level(messages))
    level = max_bump_level(messages) if messages else "patch"
    return bump_version(current, level)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("current", "next", "apply"))
    parser.add_argument(
        "version",
        nargs="?",
        help="For apply: version to write. Default: next.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "current":
        print(read_version_file())
        return 0
    if args.command == "next":
        print(next_version())
        return 0
    version = args.version or next_version()
    apply_version(version)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
