from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from typing import Any, TextIO

from research_cli.errors import MissingKeyError, ProviderHttpError
from research_cli.http import Transport
from research_cli.keys import (
    optional_bgpt_key,
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
)
from research_cli.providers import bgpt, brave, exa, firecrawl

DESCRIPTION = (
    "Agent-facing research CLI. Direct HTTP REST calls for bgpt paper search, "
    "brave search web results, exa search/contents, and firecrawl scrape/search. "
    "Do not use MCP; run this CLI."
)

EPILOG = """\
providers:
  bgpt          scientific paper search (BGPT REST)
  brave         brave search web results
  exa           Exa semantic search and page contents/fetch
  firecrawl     Firecrawl page scrape and web search

examples:
  research-cli bgpt search "CRISPR delivery neurons"
  research-cli brave search "rust async runtime"
  research-cli exa search "latest LLM evaluations"
  research-cli exa contents https://example.com
  research-cli firecrawl scrape https://example.com
  research-cli firecrawl search "web scraping python"
"""


def _shared_flags() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--base-url",
        default=argparse.SUPPRESS,
        help="Override API origin for the selected provider (fixture servers)",
    )
    shared.add_argument(
        "--timeout",
        type=float,
        default=argparse.SUPPRESS,
        help="HTTP timeout in seconds (default: 60)",
    )
    return shared


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_flags()
    parser = argparse.ArgumentParser(
        prog="research-cli",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared],
    )
    sub = parser.add_subparsers(dest="provider", required=True)

    bgpt_p = sub.add_parser("bgpt", help="BGPT scientific paper search")
    bgpt_sub = bgpt_p.add_subparsers(dest="operation", required=True)
    bgpt_search = bgpt_sub.add_parser(
        "search", help="Search papers via BGPT", parents=[shared]
    )
    bgpt_search.add_argument("query", help="Search terms")
    bgpt_search.add_argument("--num-results", type=int, default=10)
    bgpt_search.add_argument("--days-back", type=int, default=None)
    bgpt_search.add_argument("--output-format", default="evidence")

    brave_p = sub.add_parser("brave", help="brave search web results")
    brave_sub = brave_p.add_subparsers(dest="operation", required=True)
    brave_search = brave_sub.add_parser(
        "search", help="Web search via Brave Search", parents=[shared]
    )
    brave_search.add_argument("query", help="Search query")
    brave_search.add_argument("--count", type=int, default=10)

    exa_p = sub.add_parser("exa", help="Exa semantic search and contents")
    exa_sub = exa_p.add_subparsers(dest="operation", required=True)
    exa_search = exa_sub.add_parser(
        "search", help="Semantic web search via Exa", parents=[shared]
    )
    exa_search.add_argument("query", help="Search query")
    exa_search.add_argument("--num-results", type=int, default=10)
    exa_contents = exa_sub.add_parser(
        "contents",
        help="Fetch page text/highlights via Exa contents",
        parents=[shared],
    )
    exa_contents.add_argument("url", help="Page URL to fetch")

    fire_p = sub.add_parser(
        "firecrawl", help="Firecrawl page scrape and web search"
    )
    fire_sub = fire_p.add_subparsers(dest="operation", required=True)
    fire_scrape = fire_sub.add_parser(
        "scrape", help="Scrape a URL to markdown", parents=[shared]
    )
    fire_scrape.add_argument("url", help="Page URL to scrape")
    fire_search = fire_sub.add_parser(
        "search", help="Web search via Firecrawl", parents=[shared]
    )
    fire_search.add_argument("query", help="Search query")
    fire_search.add_argument("--limit", type=int, default=10)
    return parser


def _origin(args: argparse.Namespace, environ: Mapping[str, str], default: str) -> str:
    base_url = getattr(args, "base_url", None)
    if base_url:
        return base_url
    env_base = (environ.get("RESEARCH_CLI_BASE_URL") or "").strip()
    return env_base or default


def _timeout(args: argparse.Namespace) -> float:
    return float(getattr(args, "timeout", 60.0))


def _emit(payload: dict[str, Any], stdout: TextIO) -> None:
    json.dump(payload, stdout, indent=2, ensure_ascii=False)
    stdout.write("\n")


def _dispatch(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
) -> dict[str, Any]:
    timeout = _timeout(args)
    if args.provider == "bgpt":
        return bgpt.search_papers(
            args.query,
            num_results=args.num_results,
            days_back=args.days_back,
            api_key=optional_bgpt_key(environ),
            output_format=args.output_format,
            origin=_origin(args, environ, bgpt.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "brave":
        return brave.web_search(
            args.query,
            api_key=require_brave_key(environ),
            count=args.count,
            origin=_origin(args, environ, brave.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "exa" and args.operation == "search":
        return exa.search(
            args.query,
            api_key=require_exa_key(environ),
            num_results=args.num_results,
            origin=_origin(args, environ, exa.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "exa" and args.operation == "contents":
        return exa.contents(
            args.url,
            api_key=require_exa_key(environ),
            origin=_origin(args, environ, exa.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "firecrawl" and args.operation == "scrape":
        return firecrawl.scrape(
            args.url,
            api_key=require_firecrawl_key(environ),
            origin=_origin(args, environ, firecrawl.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "firecrawl" and args.operation == "search":
        return firecrawl.search(
            args.query,
            api_key=require_firecrawl_key(environ),
            limit=args.limit,
            origin=_origin(args, environ, firecrawl.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    raise ValueError(f"unknown command: {args.provider} {getattr(args, 'operation', '')}")


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code is None else int(code)
    try:
        result = _dispatch(args, environ, transport)
    except MissingKeyError as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except ProviderHttpError as exc:
        print(f"error: {exc}", file=stderr)
        return 1
    _emit(result, stdout)
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
