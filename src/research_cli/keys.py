from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from research_cli.errors import MissingKeyError

_TRUTHY = {"1", "true", "yes", "on"}


def default_env_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = (env.get("RESEARCH_CLI_ENV_FILE") or "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        base = (env.get("APPDATA") or "").strip()
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "research-cli" / "env"
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        return Path(xdg) / "research-cli" / "env"
    return Path.home() / ".config" / "research-cli" / "env"


def parse_env_file(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            parsed[key] = value
    return parsed


def load_provider_keys(environ: Mapping[str, str]) -> dict[str, str]:
    result = dict(environ)
    flag = (result.get("RESEARCH_CLI_NO_ENV_FILE") or "").strip().lower()
    if flag in _TRUTHY:
        return result
    path = default_env_path(result)
    try:
        parsed = parse_env_file(path)
    except OSError:
        return result
    for key, value in parsed.items():
        if not (result.get(key) or "").strip():
            result[key] = value
    return result


def optional_bgpt_key(environ: Mapping[str, str]) -> str | None:
    key = (environ.get("BGPT_API_KEY") or "").strip()
    return key or None


def require_brave_key(environ: Mapping[str, str]) -> str:
    key = (
        environ.get("BRAVE_API_KEY") or environ.get("BRAVE_SEARCH_API_KEY") or ""
    ).strip()
    if not key:
        raise MissingKeyError(
            "brave search",
            ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"),
        )
    return key


def require_exa_key(environ: Mapping[str, str]) -> str:
    key = (environ.get("EXA_API_KEY") or "").strip()
    if not key:
        raise MissingKeyError("exa", ("EXA_API_KEY",))
    return key


def require_firecrawl_key(environ: Mapping[str, str]) -> str:
    key = (environ.get("FIRECRAWL_API_KEY") or "").strip()
    if not key:
        raise MissingKeyError("firecrawl", ("FIRECRAWL_API_KEY",))
    return key
