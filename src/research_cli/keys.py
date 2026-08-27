from collections.abc import Mapping

from research_cli.errors import MissingKeyError


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
