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


def upsert_env_values(
    path: Path,
    values: Mapping[str, str],
    *,
    drop: tuple[str, ...] = (),
) -> None:
    """Create or patch an env file. Existing unrelated keys are kept."""
    drop_set = {name for name in drop if name}
    incoming = {
        key: value
        for key, value in values.items()
        if key and key not in drop_set
    }
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    rewritten: list[str] = []
    for line in lines:
        stripped = line.strip()
        raw = stripped[7:].strip() if stripped.startswith("export ") else stripped
        key = ""
        if raw and not raw.startswith("#") and "=" in raw:
            key = raw.partition("=")[0].strip()
        if key in drop_set:
            continue
        if key in incoming:
            rewritten.append(f"{key}={incoming[key]}")
            seen.add(key)
            continue
        rewritten.append(line)
    for key, value in incoming.items():
        if key not in seen:
            rewritten.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(rewritten)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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


def require_reddit_credentials(environ: Mapping[str, str]) -> tuple[str, str]:
    client_id = (environ.get("REDDIT_CLIENT_ID") or "").strip()
    client_secret = (environ.get("REDDIT_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise MissingKeyError(
            "reddit", ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
        )
    return client_id, client_secret


def require_x_credentials(environ: Mapping[str, str]) -> tuple[str, str]:
    auth_token = (environ.get("X_AUTH_TOKEN") or "").strip()
    ct0 = (environ.get("X_CT0") or "").strip()
    if not auth_token or not ct0:
        raise MissingKeyError("x", ("X_AUTH_TOKEN", "X_CT0"))
    return auth_token, ct0


def require_tgstat_session(environ: Mapping[str, str]) -> str:
    """Logged-in tgstat.com cookies (Premium-search), not Search API token."""
    idr = (environ.get("TGSTAT_IDR") or environ.get("TGSTAT_IDRK") or "").strip()
    sirk = (environ.get("TGSTAT_SIRK") or "").strip()
    if not idr or not sirk:
        raise MissingKeyError(
            "tgstat",
            ("TGSTAT_IDR", "TGSTAT_SIRK"),
            detail=(
                "missing tgstat.com session cookies; copy tgstat_idrk → TGSTAT_IDR "
                "and tgstat_sirk → TGSTAT_SIRK (HttpOnly; browser Application cookies)"
            ),
        )
    csrf = (environ.get("TGSTAT_CSRK") or "").strip()
    settings = (environ.get("TGSTAT_SETTINGS") or "").strip()
    parts = [f"tgstat_idrk={idr}", f"tgstat_sirk={sirk}"]
    if csrf:
        parts.append(f"_tgstat_csrk={csrf}")
    if settings:
        parts.append(f"tgstat_settings={settings}")
    return "; ".join(parts)


def require_telegram_app(environ: Mapping[str, str]) -> tuple[int, str]:
    raw_id = (environ.get("TELEGRAM_API_ID") or "").strip()
    api_hash = (environ.get("TELEGRAM_API_HASH") or "").strip()
    if not raw_id or not api_hash:
        raise MissingKeyError("telegram", ("TELEGRAM_API_ID", "TELEGRAM_API_HASH"))
    try:
        api_id = int(raw_id)
    except ValueError as exc:
        raise MissingKeyError(
            "telegram",
            ("TELEGRAM_API_ID",),
            detail="TELEGRAM_API_ID must be an integer from my.telegram.org/apps",
        ) from exc
    return api_id, api_hash


def optional_telegram_session(environ: Mapping[str, str]) -> str:
    return (environ.get("TELEGRAM_SESSION") or "").strip()


def telegram_session_file(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = (env.get("TELEGRAM_SESSION_FILE") or "").strip()
    if override:
        return Path(override).expanduser()
    return default_env_path(env).parent / "telegram.session"


def telegram_persist_paths(
    environ: Mapping[str, str],
    *,
    write: bool = True,
) -> tuple[Path | None, Path | None]:
    """Env file and sqlite session path. Disabled when RESEARCH_CLI_NO_ENV_FILE is set."""
    if not write:
        override = (environ.get("TELEGRAM_SESSION_FILE") or "").strip()
        return None, Path(override).expanduser() if override else None
    flag = (environ.get("RESEARCH_CLI_NO_ENV_FILE") or "").strip().lower()
    if flag in _TRUTHY:
        override = (environ.get("TELEGRAM_SESSION_FILE") or "").strip()
        return None, Path(override).expanduser() if override else None
    env_path = default_env_path(environ)
    return env_path, telegram_session_file(environ)


def require_telegram_session(environ: Mapping[str, str]) -> str:
    session = optional_telegram_session(environ)
    if session:
        return session
    flag = (environ.get("RESEARCH_CLI_NO_ENV_FILE") or "").strip().lower()
    isolated = flag in _TRUTHY
    path = telegram_session_file(environ)
    if isolated and not (environ.get("TELEGRAM_SESSION_FILE") or "").strip():
        raise MissingKeyError(
            "telegram",
            ("TELEGRAM_SESSION",),
            detail=(
                "missing telegram session; run research-cli telegram login once "
                "(saved under ~/.config/research-cli/)"
            ),
        )
    try:
        if path.is_file() and path.stat().st_size > 0:
            return ""
    except OSError:
        pass
    raise MissingKeyError(
        "telegram",
        ("TELEGRAM_SESSION",),
        detail=(
            "missing telegram session; run research-cli telegram login once "
            "(saved under ~/.config/research-cli/)"
        ),
    )
