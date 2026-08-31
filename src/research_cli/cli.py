from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any, TextIO

from research_cli import __version__
from research_cli.errors import MissingKeyError, ProviderHttpError, UpdateError
from research_cli.http import Transport
from research_cli.keys import (
    default_env_path,
    load_provider_keys,
    optional_bgpt_key,
    optional_telegram_session,
    optional_tgstat_session,
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
    require_reddit_credentials,
    require_telegram_app,
    require_telegram_session,
    require_tgstat_session,
    require_x_credentials,
    telegram_persist_paths,
)
from research_cli.providers import bgpt, brave, exa, exploitdb, firecrawl, malpedia, reddit, sploitus, telegram, tgstat, x
from research_cli.providers import firecrawl_papers as papers
from research_cli.update import run_self_update, spawn_background_update

DESCRIPTION = (
    "Agent-facing research CLI. Direct HTTP REST calls for bgpt paper search, "
    "brave search / llm-context, exa search/contents, firecrawl "
    "scrape/search/map/papers, reddit search/thread/subreddit, sploitus "
    "exploit/hacktool search, exploit-db exploits/GHDB/papers/shellcodes, "
    "malpedia malware families/actors/YARA/bib/MISP (guest), x "
    "(Twitter) search/thread via the logged-in web GraphQL client, and "
    "telegram post search plus user-session get/download (Telethon MTProto, "
    "not Bot API; does not join chats). Search cookies vs Telegram session "
    "errors name tgstat or telegram. Do not use MCP; run this CLI."
)

EPILOG = """\
providers:
  bgpt          scientific paper search (BGPT REST)
  brave         brave search web results and llm-context
  exa           Exa semantic search and page contents/fetch
  firecrawl     Firecrawl scrape, search, map, and research papers
  reddit        Reddit post search, thread comments, and subreddit listings (OAuth)
  sploitus      Sploitus exploit/hacktool search, CVE, product, latest (no API key)
  exploitdb     Exploit-DB search, latest, GHDB, papers, shellcodes (no API key)
  malpedia      Malpedia families, actors, YARA, bib, MISP, references (guest)
  x             X (Twitter) post search and tweet threads (cookie session)
  telegram      Telegram posts (TGStat index) and user-session files (Telethon; no join)
  help          setup topics (install, keys)

examples:
  research-cli help install
  research-cli help keys
  research-cli bgpt search "CRISPR delivery neurons"
  research-cli brave search "rust async runtime" --freshness pw
  research-cli brave llm-context "best practices for RAG"
  research-cli exa search "LLM evals" --include-domains arxiv.org --category "research paper"
  research-cli exa contents https://example.com
  research-cli firecrawl scrape https://example.com --live
  research-cli firecrawl search "site:arxiv.org transformers" --categories research
  research-cli firecrawl map https://docs.firecrawl.dev --search webhook
  research-cli firecrawl papers search "CRISPR off-target T cells" --k 10
  research-cli firecrawl papers inspect arxiv:1706.03762
  research-cli firecrawl papers read arxiv:1706.03762 --question "what is the architecture?"
  research-cli firecrawl papers related arxiv:1706.03762 --intent "efficient attention"
  research-cli reddit search "CRISPR neurons" --sort top --time week
  research-cli reddit thread abc123 --sort top --limit 50
  research-cli reddit subreddit rust --sort top --time week
  research-cli sploitus search "CVE-2021-44228" --sort score
  research-cli sploitus search "c2" --type tools
  research-cli sploitus exploit EDB-ID:50592
  research-cli sploitus cve CVE-2021-44228
  research-cli sploitus product wordpress
  research-cli sploitus latest
  research-cli sploitus home
  research-cli sploitus autocomplete log4
  research-cli exploitdb search "CVE-2021-44228" --type remote --platform java
  research-cli exploitdb latest
  research-cli exploitdb exploit 50592
  research-cli exploitdb raw 50592
  research-cli exploitdb download 50592
  research-cli exploitdb papers "polkit" --language english
  research-cli exploitdb paper 50981
  research-cli exploitdb shellcodes "reverse tcp" --platform linux
  research-cli exploitdb shellcode 52599
  research-cli exploitdb ghdb "inurl:admin" --category 9
  research-cli exploitdb dork 2
  research-cli exploitdb authors leon
  research-cli exploitdb stats
  research-cli malpedia search emotet
  research-cli malpedia family win.emotet
  research-cli malpedia actor apt28
  research-cli malpedia yara win.emotet
  research-cli malpedia yara win.emotet --zip --output /tmp
  research-cli malpedia families --limit 20
  research-cli malpedia families --full --limit 5
  research-cli malpedia actors --limit 20
  research-cli malpedia bib --family win.owowa
  research-cli malpedia misp --output /tmp
  research-cli malpedia references --url https://securelist.com/goffee-apt-new-attacks/116139/
  research-cli malpedia yara-list --family win.emotet
  research-cli malpedia yara-dump --tlp white --output /tmp --timeout 180
  research-cli malpedia yara-after 2026-01-01
  research-cli malpedia version
  research-cli x search "VMProtect LLVM" --product latest --count 20
  research-cli x search "breaking news" --product top --count 20
  research-cli x search "QUERY" --compact --fields id,url,text,user,likes
  research-cli x thread 2069347283918000383
  research-cli x thread https://x.com/user/status/2069347283918000383
  research-cli telegram search "llvm obfuscation" --limit 20
  research-cli telegram search "QUERY" --peer-type channel --sort views --views-range 1k-10k --forwards hide
  research-cli telegram search "QUERY" --download /tmp --media document --allow-large
  research-cli telegram sources "QUERY"
  research-cli telegram mentions "QUERY" --group month
  research-cli telegram export "QUERY" --output /tmp
  research-cli telegram catalogs
  research-cli telegram login --api-id 123456 --api-hash HASH --phone +15551234567
  research-cli telegram login --code 12345
  research-cli telegram me
  research-cli telegram discover "reverse engineering"
  research-cli telegram history @durov --limit 20
  research-cli telegram resolve durov
  research-cli telegram resolve https://t.me/joinchat/AbCdefgh
  research-cli telegram get https://t.me/durov/1
  research-cli telegram download https://t.me/durov/1 --output /tmp
  research-cli telegram download https://t.me/joinchat/AbCdefgh/12 --output /tmp
"""


INSTALL_DOC_URL = (
    "https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main"
    "/skills/research-cli/INSTALL.md"
)
HELP_DOC_URLS = {"install": INSTALL_DOC_URL}
HELP_TOPICS = {
    "install": """\
# Install research-cli

Goal: `research-cli --version` works on PATH. Then run the skill playbook.

## Frozen binary (no Python)

```bash
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
base="https://github.com/ErcinDedeoglu/research-cli/releases/latest/download"
os="$(uname -s)"; arch="$(uname -m)"
case "$os-$arch" in
  Darwin-arm64) asset=research-cli-Darwin-arm64 ;;
  Linux-x86_64) asset=research-cli-Linux-x86_64 ;;
  Linux-aarch64|Linux-arm64) asset=research-cli-Linux-aarch64 ;;
  *) echo "unsupported: $os $arch"; exit 1 ;;
esac
curl -fsSL -o "$HOME/.local/bin/research-cli" "$base/$asset"
chmod +x "$HOME/.local/bin/research-cli"
command -v research-cli
```

Windows: download `$base/research-cli-Windows-x86_64.exe` as `research-cli.exe` on PATH.

macOS quarantine: `xattr -d com.apple.quarantine "$HOME/.local/bin/research-cli"`.

## Already on PATH

`research-cli --self-update`. `research-cli --version` is SemVer.

## Zipapp / source

- zipapp: `$base/research-cli.pyz` then `python3 research-cli.pyz`
- checkout: `pip install -e .`

Then write keys (`research-cli help keys`) and run search from the skill.
""",
    "keys": """\
Provider API keys and cookies.

File: `$HOME/.config/research-cli/env` (Windows: `%APPDATA%\\research-cli\\env`), chmod 600. Process env overrides the file.

```
BRAVE_API_KEY=
EXA_API_KEY=
FIRECRAWL_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
# BGPT_API_KEY=
# X_AUTH_TOKEN=
# X_CT0=
# TGSTAT_IDR=
# TGSTAT_SIRK=
# TGSTAT_CSRK=
# TGSTAT_SETTINGS=
# TELEGRAM_API_ID=
# TELEGRAM_API_HASH=
# TELEGRAM_SESSION=
# TELEGRAM_SESSION_FILE=
```

Provider key map:

  bgpt          BGPT_API_KEY (optional; free tier works without it)
  brave         BRAVE_API_KEY or BRAVE_SEARCH_API_KEY
  exa           EXA_API_KEY
  firecrawl     FIRECRAWL_API_KEY
  reddit        REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
  x             X_AUTH_TOKEN and X_CT0 (browser `auth_token` and `ct0` cookies)
  tgstat        TGSTAT_IDR (cookie tgstat_idrk) and TGSTAT_SIRK (cookie tgstat_sirk). Optional TGSTAT_CSRK, TGSTAT_SETTINGS. Used by `telegram search` / sources / mentions / export. Logged-in tgstat.com Premium-search, not Search API. Missing/dead cookies exit 2 and name **tgstat**.
  telegram      TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION. Used by `telegram login` / history / get / download. `telegram login` writes them plus `telegram.session` next to the env file. Later file commands reuse that session (no phone/code). Optional TELEGRAM_SESSION_FILE. Not a BotFather token. Missing/dead session exit 2 and name **telegram**.
  sploitus      none
  exploitdb     none
  malpedia      none (guest access)

Missing brave, exa, firecrawl, reddit, x, tgstat, or telegram keys exit 2 and name the backend (tgstat vs telegram). Dead x/tgstat cookies and dead telegram sessions also exit 2; if those sessions are unset, skip that telegram command rather than blocking the other providers. Never commit keys, cookies, TELEGRAM_SESSION, TGSTAT_IDR, or TGSTAT_SIRK.
""",
}
HELP_TOPIC_ALIASES = {"installation": "install"}


def help_topic_payload(topic: str | None) -> dict[str, Any]:
    if not (topic or "").strip():
        return {
            "provider": "help",
            "topics": sorted(HELP_TOPICS),
            "aliases": dict(HELP_TOPIC_ALIASES),
            "hint": "research-cli help install",
        }
    key = HELP_TOPIC_ALIASES.get(topic.strip().lower(), topic.strip().lower())
    body = HELP_TOPICS.get(key)
    if body is None:
        known = ", ".join(sorted(HELP_TOPICS))
        raise ProviderHttpError(
            "help", 0, f"unknown topic {topic!r}; try: {known}"
        )
    payload = {"provider": "help", "topic": key, "body": body}
    url = HELP_DOC_URLS.get(key)
    if url:
        payload["url"] = url
    return payload


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [item.strip() for item in value.split(",") if item.strip()]
    return parts or None


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


def _tgstat_filter_flags() -> argparse.ArgumentParser:
    filters = argparse.ArgumentParser(add_help=False)
    filters.add_argument(
        "--peer-type",
        choices=tgstat.PEER_TYPES,
        default="all",
        help="all (default), channel, or chat",
    )
    filters.add_argument("--start", help="From date (YYYY-MM-DD or DD.MM.YYYY)")
    filters.add_argument("--end", help="To date (YYYY-MM-DD or DD.MM.YYYY)")
    filters.add_argument(
        "--sort",
        choices=tgstat.SORTS,
        default="date",
        help="date (default) or views",
    )
    filters.add_argument(
        "--country",
        help="Channel geo slug (telegram catalogs)",
    )
    filters.add_argument(
        "--language",
        help="Content language slug (telegram catalogs)",
    )
    filters.add_argument(
        "--category",
        help="Channel topic slug (telegram catalogs)",
    )
    filters.add_argument("--minus-words", help="Space-separated exclusion words")
    filters.add_argument(
        "--views-range",
        choices=tgstat.VIEWS_RANGES,
        default="all",
        help="all (default), lt1000, 1k-10k, or 10k",
    )
    filters.add_argument(
        "--channel-id",
        help="Pin to one source (numeric id from telegram sources)",
    )
    filters.add_argument(
        "--source-sort",
        choices=tgstat.SOURCE_SORTS,
        default="members",
        help="Source list: members (default) or freq",
    )
    filters.add_argument(
        "--forwards",
        choices=tgstat.FORWARDS,
        default="all",
        help="all (default), hide, or only",
    )
    filters.add_argument(
        "--hide-forwards",
        action="store_true",
        help="Same as --forwards hide",
    )
    filters.add_argument(
        "--hide-deleted",
        action="store_true",
        help="Drop posts TGStat marked deleted",
    )
    filters.add_argument(
        "--strong", action="store_true", help="Exact tokens (no morphology)"
    )
    filters.add_argument(
        "--extended", action="store_true", help="Extended query syntax"
    )
    filters.add_argument(
        "--only-mentioned",
        action="store_true",
        help="Only posts that mention channels",
    )
    return filters


def _tgstat_filter_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "peer_type": args.peer_type,
        "start": args.start,
        "end": args.end,
        "sort": args.sort,
        "country": args.country,
        "language": args.language,
        "category": args.category,
        "minus_words": args.minus_words,
        "views_range": args.views_range,
        "channel_id": args.channel_id,
        "source_sort": args.source_sort,
        "forwards": args.forwards,
        "hide_forwards": args.hide_forwards,
        "hide_deleted": args.hide_deleted,
        "strong": args.strong,
        "extended": args.extended,
        "only_mentioned": args.only_mentioned,
    }


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_flags()
    tgstat_filters = _tgstat_filter_flags()
    parser = argparse.ArgumentParser(
        prog="research-cli",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared],
    )
    parser.add_argument(
        "--self-update",
        action="store_true",
        help="Replace this frozen binary or zipapp with the latest GitHub release",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"research-cli {__version__}",
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

    brave_p = sub.add_parser("brave", help="brave search web results and llm-context")
    brave_sub = brave_p.add_subparsers(dest="operation", required=True)
    brave_search = brave_sub.add_parser(
        "search", help="Web search via Brave Search", parents=[shared]
    )
    brave_search.add_argument("query", help="Search query")
    brave_search.add_argument("--count", type=int, default=10)
    brave_search.add_argument("--country", default=None)
    brave_search.add_argument(
        "--freshness",
        default=None,
        help="pd (day), pw (week), pm (month), py (year), or YYYY-MM-DDtoYYYY-MM-DD",
    )
    brave_search.add_argument("--offset", type=int, default=None)
    brave_llm = brave_sub.add_parser(
        "llm-context",
        help="Ranked page chunks via Brave LLM Context",
        parents=[shared],
    )
    brave_llm.add_argument("query", help="Search query")
    brave_llm.add_argument("--count", type=int, default=20)
    brave_llm.add_argument("--country", default=None)
    brave_llm.add_argument("--freshness", default=None)

    exa_p = sub.add_parser("exa", help="Exa semantic search and contents")
    exa_sub = exa_p.add_subparsers(dest="operation", required=True)
    exa_search = exa_sub.add_parser(
        "search", help="Semantic web search via Exa", parents=[shared]
    )
    exa_search.add_argument("query", help="Search query")
    exa_search.add_argument("--num-results", type=int, default=10)
    exa_search.add_argument("--include-domains", default=None)
    exa_search.add_argument("--exclude-domains", default=None)
    exa_search.add_argument("--category", default=None)
    exa_search.add_argument("--start-published", default=None)
    exa_search.add_argument("--end-published", default=None)
    exa_search.add_argument("--highlights", action="store_true")
    exa_search.add_argument("--text", action="store_true")
    exa_contents = exa_sub.add_parser(
        "contents",
        help="Fetch page text/highlights via Exa contents",
        parents=[shared],
    )
    exa_contents.add_argument("url", help="Page URL to fetch")

    fire_p = sub.add_parser(
        "firecrawl", help="Firecrawl scrape, search, map, and papers"
    )
    fire_sub = fire_p.add_subparsers(dest="operation", required=True)
    fire_scrape = fire_sub.add_parser(
        "scrape", help="Scrape a URL to markdown", parents=[shared]
    )
    fire_scrape.add_argument("url", help="Page URL to scrape")
    fire_scrape.add_argument("--formats", default="markdown")
    fire_scrape.add_argument(
        "--live",
        action="store_true",
        help="Force a live fetch (maxAge=0)",
    )
    fire_scrape.add_argument("--max-age", type=int, default=None)
    fire_scrape.add_argument("--no-main-content", action="store_true")
    fire_search = fire_sub.add_parser(
        "search", help="Web search via Firecrawl", parents=[shared]
    )
    fire_search.add_argument("query", help="Search query")
    fire_search.add_argument("--limit", type=int, default=10)
    fire_search.add_argument("--categories", default=None)
    fire_search.add_argument("--include-domains", default=None)
    fire_search.add_argument("--exclude-domains", default=None)
    fire_search.add_argument(
        "--scrape",
        action="store_true",
        help="Also scrape each hit to markdown",
    )
    fire_map = fire_sub.add_parser(
        "map", help="List URLs under a site", parents=[shared]
    )
    fire_map.add_argument("url", help="Site URL to map")
    fire_map.add_argument("--search", default=None)
    fire_map.add_argument("--limit", type=int, default=50)
    papers_p = fire_sub.add_parser(
        "papers", help="Firecrawl research paper index"
    )
    papers_sub = papers_p.add_subparsers(dest="papers_op", required=True)
    p_search = papers_sub.add_parser("search", help="Search paper abstracts", parents=[shared])
    p_search.add_argument("query")
    p_search.add_argument("--k", type=int, default=40)
    p_search.add_argument("--authors", default=None)
    p_search.add_argument("--categories", default=None)
    p_search.add_argument("--from", dest="from_date", default=None)
    p_search.add_argument("--to", dest="to_date", default=None)
    p_inspect = papers_sub.add_parser("inspect", help="Inspect paper metadata", parents=[shared])
    p_inspect.add_argument("paper_id")
    p_read = papers_sub.add_parser("read", help="Read paper passages for a question", parents=[shared])
    p_read.add_argument("paper_id")
    p_read.add_argument("--question", required=True)
    p_read.add_argument("--k", type=int, default=4)
    p_related = papers_sub.add_parser("related", help="Citation-graph related papers", parents=[shared])
    p_related.add_argument("paper_id")
    p_related.add_argument("--intent", required=True)
    p_related.add_argument("--mode", default="similar", choices=("similar", "citers", "references"))
    p_related.add_argument("--k", type=int, default=40)
    p_related.add_argument("--anchors", default=None)

    reddit_p = sub.add_parser(
        "reddit", help="Reddit post search, threads, and subreddit listings"
    )
    reddit_sub = reddit_p.add_subparsers(dest="operation", required=True)
    reddit_search = reddit_sub.add_parser(
        "search", help="Search posts via Reddit", parents=[shared]
    )
    reddit_search.add_argument("query", help="Search terms")
    reddit_search.add_argument(
        "--sort",
        default="relevance",
        choices=("relevance", "hot", "top", "new", "comments"),
    )
    reddit_search.add_argument(
        "--time",
        default="all",
        choices=("hour", "day", "week", "month", "year", "all"),
        help="Time window (Reddit t=)",
    )
    reddit_search.add_argument("--limit", type=int, default=25)
    reddit_search.add_argument(
        "--subreddit",
        default=None,
        help="Limit search to one subreddit (without r/)",
    )
    reddit_thread = reddit_sub.add_parser(
        "thread",
        help="Read a post and its comments",
        parents=[shared],
    )
    reddit_thread.add_argument(
        "target", help="Post ID, t3_ ID, or Reddit comments URL"
    )
    reddit_thread.add_argument(
        "--sort",
        default="best",
        choices=("best", "top", "new", "controversial", "old", "qa"),
    )
    reddit_thread.add_argument("--limit", type=int, default=50)
    reddit_thread.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Comment tree depth (Reddit depth=)",
    )
    reddit_listing = reddit_sub.add_parser(
        "subreddit",
        help="List posts in a subreddit",
        parents=[shared],
    )
    reddit_listing.add_argument(
        "name", help="Subreddit name (without r/)"
    )
    reddit_listing.add_argument(
        "--sort",
        default="hot",
        choices=("hot", "new", "top", "rising", "controversial"),
    )
    reddit_listing.add_argument(
        "--time",
        default="all",
        choices=("hour", "day", "week", "month", "year", "all"),
        help="Time window for top/controversial (Reddit t=)",
    )
    reddit_listing.add_argument("--limit", type=int, default=25)

    sploitus_p = sub.add_parser(
        "sploitus", help="Sploitus exploit and hacktool search"
    )
    sploitus_sub = sploitus_p.add_subparsers(dest="operation", required=True)
    sploitus_search = sploitus_sub.add_parser(
        "search", help="Search exploits or hacktools via Sploitus", parents=[shared]
    )
    sploitus_search.add_argument("query", help="CVE, product, or exploit terms")
    sploitus_search.add_argument(
        "--type",
        dest="search_type",
        default="exploits",
        choices=("exploits", "tools"),
        help="UI toggle: Exploits (PoC/MSF) or Tools (hacktools)",
    )
    sploitus_search.add_argument(
        "--sort",
        default="default",
        choices=("default", "relevance", "date", "score", "cvss"),
        help="UI sort: Relevance (default), Date, Score (CVSS)",
    )
    sploitus_search.add_argument("--offset", type=int, default=0)
    sploitus_search.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max hits (server pages 10 at a time)",
    )
    sploitus_search.add_argument(
        "--source",
        action="store_true",
        help="Include full exploit source in each hit (large)",
    )
    sploitus_exploit = sploitus_sub.add_parser(
        "exploit",
        help="Read one exploit page (source + metadata)",
        parents=[shared],
    )
    sploitus_exploit.add_argument(
        "target", help="Exploit id or https://sploitus.com/exploit?id=..."
    )
    sploitus_cve = sploitus_sub.add_parser(
        "cve",
        help="List known exploits for a CVE",
        parents=[shared],
    )
    sploitus_cve.add_argument("cve_id", help="CVE-YYYY-NNNNN")
    sploitus_cve.add_argument("--limit", type=int, default=100)
    sploitus_product = sploitus_sub.add_parser(
        "product",
        help="List exploited CVEs for a product",
        parents=[shared],
    )
    sploitus_product.add_argument("name", help="Product name or /product/slug")
    sploitus_product.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max CVE rows (site pages 50 at a time)",
    )
    sploitus_latest = sploitus_sub.add_parser(
        "latest",
        help="Newest exploits in the index",
        parents=[shared],
    )
    sploitus_latest.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max hits (site pages 50 at a time)",
    )
    sploitus_home = sploitus_sub.add_parser(
        "home",
        help="Homepage widgets: trending CVEs, popular exploits, latest",
        parents=[shared],
    )
    sploitus_ac = sploitus_sub.add_parser(
        "autocomplete",
        help="Typeahead suggestions",
        parents=[shared],
    )
    sploitus_ac.add_argument("query", help="Partial query")

    edb_p = sub.add_parser(
        "exploitdb", help="Exploit-DB exploits, GHDB, papers, and shellcodes"
    )
    edb_sub = edb_p.add_subparsers(dest="operation", required=True)
    edb_search = edb_sub.add_parser(
        "search", help="Search exploits (DataTables JSON)", parents=[shared]
    )
    edb_search.add_argument("query", help="Title terms")
    edb_search.add_argument(
        "--type",
        dest="search_type",
        default=None,
        choices=exploitdb.SEARCH_TYPES,
        help="UI type: dos, local, remote, shellcode, papers, webapps, hardware",
    )
    edb_search.add_argument("--platform", help="UI platform slug (java, php, windows, …)")
    edb_search.add_argument("--port", help="UI port filter")
    edb_search.add_argument("--cve", help="CVE-YYYY-NNNNN or YYYY-NNNNN")
    edb_search.add_argument("--text", help="Full-text exploit content")
    edb_search.add_argument("--author", help="Author name or numeric id")
    edb_search.add_argument("--tag", help="Tag id or name (sqli, xss, poc, …)")
    edb_search.add_argument("--verified", action="store_true")
    edb_search.add_argument("--hasapp", action="store_true", help="Has vulnerable app attached")
    edb_search.add_argument("--nomsf", action="store_true", help="Exclude Metasploit")
    edb_search.add_argument("--offset", type=int, default=0)
    edb_search.add_argument("--limit", type=int, default=15)
    edb_latest = edb_sub.add_parser(
        "latest", help="Homepage latest exploits", parents=[shared]
    )
    edb_latest.add_argument("--offset", type=int, default=0)
    edb_latest.add_argument("--limit", type=int, default=15)
    edb_exploit = edb_sub.add_parser(
        "exploit", help="Exploit hub /exploits/{id}", parents=[shared]
    )
    edb_exploit.add_argument("target", help="EDB id or https://www.exploit-db.com/exploits/…")
    edb_raw = edb_sub.add_parser(
        "raw", help="Plain-text PoC /raw/{id}", parents=[shared]
    )
    edb_raw.add_argument("target", help="EDB id")
    edb_download = edb_sub.add_parser(
        "download",
        help="Save /download/{id} to disk (exploit, paper, shellcode, or attached app)",
        parents=[shared],
    )
    edb_download.add_argument("target", help="EDB id")
    edb_download.add_argument(
        "--output",
        "-o",
        help="File or directory (default: cwd, name from Content-Disposition)",
    )
    edb_papers = edb_sub.add_parser(
        "papers", help="Papers table /papers", parents=[shared]
    )
    edb_papers.add_argument("query", nargs="?", default=None, help="Quick search")
    edb_papers.add_argument("--language", help="UI language (english, arabic, spanish, …)")
    edb_papers.add_argument("--platform", help="UI platform slug")
    edb_papers.add_argument("--author", help="Author numeric id")
    edb_papers.add_argument("--offset", type=int, default=0)
    edb_papers.add_argument("--limit", type=int, default=15)
    edb_paper = edb_sub.add_parser(
        "paper", help="Paper hub /docs/{id}", parents=[shared]
    )
    edb_paper.add_argument("target", help="Paper EDB id")
    edb_shellcodes = edb_sub.add_parser(
        "shellcodes", help="Shellcodes table /shellcodes", parents=[shared]
    )
    edb_shellcodes.add_argument("query", nargs="?", default=None, help="Quick search")
    edb_shellcodes.add_argument("--platform", help="UI platform slug")
    edb_shellcodes.add_argument("--author", help="Author numeric id")
    edb_shellcodes.add_argument("--offset", type=int, default=0)
    edb_shellcodes.add_argument("--limit", type=int, default=15)
    edb_shellcode = edb_sub.add_parser(
        "shellcode", help="Shellcode hub /shellcodes/{id}", parents=[shared]
    )
    edb_shellcode.add_argument("target", help="Shellcode EDB id")
    edb_ghdb = edb_sub.add_parser(
        "ghdb", help="Google Hacking Database", parents=[shared]
    )
    edb_ghdb.add_argument("query", nargs="?", default=None, help="Quick search / dork text")
    edb_ghdb.add_argument(
        "--category",
        help="Category id 1-14 or title (e.g. 9 or 'Files Containing Passwords')",
    )
    edb_ghdb.add_argument("--author", help="Author numeric id")
    edb_ghdb.add_argument("--offset", type=int, default=0)
    edb_ghdb.add_argument("--limit", type=int, default=15)
    edb_dork = edb_sub.add_parser(
        "dork", help="GHDB dork /ghdb/{id}", parents=[shared]
    )
    edb_dork.add_argument("target", help="GHDB id")
    edb_authors = edb_sub.add_parser(
        "authors", help="Author typeahead or lookup by id", parents=[shared]
    )
    edb_authors.add_argument("query", help="Name fragment or numeric author id")
    edb_sub.add_parser(
        "stats",
        help="Database counts (exploits/papers/shellcodes/GHDB)",
        parents=[shared],
    )

    mal_p = sub.add_parser(
        "malpedia", help="Malpedia malware families, actors, YARA, bib, MISP"
    )
    mal_sub = mal_p.add_subparsers(dest="operation", required=True)
    mal_search = mal_sub.add_parser(
        "search", help="Find families and actors by name fragment", parents=[shared]
    )
    mal_search.add_argument("query", help="Name fragment (emotet, apt28, …)")
    mal_family = mal_sub.add_parser(
        "family", help="Family metadata /api/get/family/{id}", parents=[shared]
    )
    mal_family.add_argument("target", help="Family id (win.emotet)")
    mal_actor = mal_sub.add_parser(
        "actor", help="Actor metadata /api/get/actor/{id}", parents=[shared]
    )
    mal_actor.add_argument("target", help="Actor id (apt28)")
    mal_yara = mal_sub.add_parser(
        "yara", help="YARA rules for a family (guest TLP white)", parents=[shared]
    )
    mal_yara.add_argument("target", help="Family id")
    mal_yara.add_argument(
        "--zip",
        dest="as_zip",
        action="store_true",
        help="Download /api/get/yara/{id}/zip instead of JSON",
    )
    mal_yara.add_argument(
        "--output",
        "-o",
        help="File or directory for --zip (default: cwd, name from Content-Disposition)",
    )
    mal_families = mal_sub.add_parser(
        "families",
        help="List family ids, or --full /api/get/families",
        parents=[shared],
    )
    mal_families.add_argument("--limit", type=int, default=None)
    mal_families.add_argument(
        "--full",
        action="store_true",
        help="GET /api/get/families (~4MB JSON of every family)",
    )
    mal_families.add_argument(
        "--output",
        "-o",
        help="Write the raw JSON body to a file or directory",
    )
    mal_actors = mal_sub.add_parser(
        "actors",
        help="List actor ids, or --full /api/get/actors",
        parents=[shared],
    )
    mal_actors.add_argument("--limit", type=int, default=None)
    mal_actors.add_argument(
        "--full",
        action="store_true",
        help="GET /api/get/actors (~1MB JSON of every actor)",
    )
    mal_actors.add_argument(
        "--output",
        "-o",
        help="Write the raw JSON body to a file or directory",
    )
    mal_bib = mal_sub.add_parser(
        "bib", help="BibTeX library (all, or one family/actor)", parents=[shared]
    )
    mal_bib_id = mal_bib.add_mutually_exclusive_group()
    mal_bib_id.add_argument("--family", help="Family id (win.owowa)")
    mal_bib_id.add_argument("--actor", help="Actor id (goffee)")
    mal_bib.add_argument(
        "--output",
        "-o",
        help="Write the .bib body to a file or directory",
    )
    mal_misp = mal_sub.add_parser(
        "misp", help="MISP galaxy cluster dump (~4MB)", parents=[shared]
    )
    mal_misp.add_argument(
        "--output",
        "-o",
        help="Write the raw JSON body to a file or directory",
    )
    mal_refs = mal_sub.add_parser(
        "references",
        help="URL → family/actor map (~4.7MB; filter with --url)",
        parents=[shared],
    )
    mal_refs.add_argument(
        "--url",
        help="Return only the mapping for this reference URL",
    )
    mal_refs.add_argument(
        "--output",
        "-o",
        help="Write the raw JSON body to a file or directory",
    )
    mal_yara_list = mal_sub.add_parser(
        "yara-list", help="Index of guest YARA paths per family", parents=[shared]
    )
    mal_yara_list.add_argument("--family", help="Limit to one family id")
    mal_dump = mal_sub.add_parser(
        "yara-dump",
        help="Bulk YARA (writes a .yar/.zip; guest TLP white == green)",
        parents=[shared],
    )
    mal_dump_kind = mal_dump.add_mutually_exclusive_group(required=True)
    mal_dump_kind.add_argument(
        "--tlp",
        choices=malpedia.TLPS,
        help="GET /api/get/yara/tlp_{white|green|amber}/raw or /zip",
    )
    mal_dump_kind.add_argument(
        "--auto",
        dest="auto_rules",
        action="store_true",
        help="GET /api/get/yara/auto/raw (YARA-Signator rules)",
    )
    mal_dump.add_argument(
        "--zip",
        dest="as_zip",
        action="store_true",
        help="Download the zip bundle instead of concatenated .yar",
    )
    mal_dump.add_argument(
        "--output",
        "-o",
        help="File or directory (default: cwd, name from Content-Disposition)",
    )
    mal_after = mal_sub.add_parser(
        "yara-after",
        help="YARA rules newer than YYYY-MM-DD (JSON)",
        parents=[shared],
    )
    mal_after.add_argument("date", help="YYYY-MM-DD")
    mal_after.add_argument(
        "--output",
        "-o",
        help="Write the raw JSON body to a file or directory",
    )
    mal_sub.add_parser("version", help="Malpedia catalog version", parents=[shared])

    x_p = sub.add_parser(
        "x", help="X (Twitter) search and tweet threads (cookie session)"
    )
    x_sub = x_p.add_subparsers(dest="operation", required=True)
    x_search = x_sub.add_parser(
        "search",
        help="GraphQL SearchTimeline (Latest/Top/People/Photos)",
        parents=[shared],
    )
    x_search.add_argument("query", help="Search terms (X operators like from:user work)")
    x_search.add_argument("--count", type=int, default=20, help="Page size (default 20)")
    x_search.add_argument(
        "--product",
        choices=("latest", "top", "people", "media"),
        default="latest",
        help="Timeline tab (default latest)",
    )
    x_search.add_argument("--cursor", help="Bottom cursor from a previous page")
    x_search.add_argument(
        "--compact",
        action="store_true",
        help="Minified JSON (single line; still valid JSON)",
    )
    x_search.add_argument(
        "--fields",
        help="Comma-separated result keys (id,url,text,user,likes,…)",
    )
    x_thread = x_sub.add_parser(
        "thread",
        help="GraphQL TweetDetail for a tweet id or status URL",
        parents=[shared],
    )
    x_thread.add_argument(
        "target", help="Tweet id or https://x.com/user/status/{id}"
    )
    x_thread.add_argument("--cursor", help="Bottom cursor from a previous page")
    x_thread.add_argument(
        "--compact",
        action="store_true",
        help="Minified JSON (single line; still valid JSON)",
    )
    x_thread.add_argument(
        "--fields",
        help="Comma-separated tweet/reply keys (id,url,text,user,likes,…)",
    )
    tg_p = sub.add_parser(
        "telegram",
        help="Telegram posts (TGStat index) and user-session files (Telethon, not Bot API)",
    )
    tg_sub = tg_p.add_subparsers(dest="operation", required=True)
    tg_search = tg_sub.add_parser(
        "search",
        help="Public Telegram post index via tgstat.com cookies (20/page, max 1000)",
        parents=[shared, tgstat_filters],
    )
    tg_search.add_argument("query", help="Search terms")
    tg_search.add_argument(
        "--limit", type=int, default=20, help="Max posts (default 20, cap 1000)"
    )
    tg_search.add_argument(
        "--offset", type=int, default=0, help="Start offset (steps of 20, cap 980)"
    )
    tg_search.add_argument(
        "--download",
        metavar="DIR",
        help="Inspect via Telegram session and save real files into DIR",
    )
    tg_search.add_argument(
        "--media",
        choices=tgstat.FILE_MEDIA_TYPES,
        help="Keep document, photo, or video (Telegram classification)",
    )
    tg_search.add_argument(
        "--private",
        action="store_true",
        help="Include private joinchat hits (skipped by default)",
    )
    tg_search.add_argument(
        "--allow-large",
        action="store_true",
        help="Download files larger than 25MB",
    )
    tg_search.add_argument(
        "--jobs",
        type=int,
        default=tgstat.DOWNLOAD_JOBS,
        help="Concurrent get/download on one Telegram session (default 4)",
    )
    tg_sources = tg_sub.add_parser(
        "sources",
        help="Mentioning channels for a query (ids for --channel-id)",
        parents=[shared, tgstat_filters],
    )
    tg_sources.add_argument("query", help="Search terms")
    tg_mentions = tg_sub.add_parser(
        "mentions",
        help="Mentions/reach chart (day or month)",
        parents=[shared, tgstat_filters],
    )
    tg_mentions.add_argument("query", help="Search terms")
    tg_mentions.add_argument(
        "--group",
        choices=tgstat.CHART_GROUPS,
        default="day",
        help="day (default) or month",
    )
    tg_export = tg_sub.add_parser(
        "export",
        help="Download index hits as xlsx (tgstat.com cookies)",
        parents=[shared, tgstat_filters],
    )
    tg_export.add_argument("query", help="Search terms")
    tg_export.add_argument(
        "--output",
        "-o",
        help="File or directory (default: cwd, name from Content-Disposition)",
    )
    tg_sub.add_parser(
        "catalogs",
        help="Country, language, category, and filter value lists",
        parents=[shared],
    )
    tg_login = tg_sub.add_parser(
        "login",
        help="One-time user login; writes TELEGRAM_* into the env file",
        parents=[shared],
    )
    tg_login.add_argument("--phone", help="Phone with country code (+1555…). First step only")
    tg_login.add_argument("--code", help="Login code from Telegram (second step)")
    tg_login.add_argument(
        "--phone-code-hash",
        help="Override pending hash (default: TELEGRAM_PHONE_CODE_HASH from env)",
    )
    tg_login.add_argument("--password", help="2FA password if Telegram asks")
    tg_login.add_argument(
        "--session",
        help="Override pending StringSession (default: TELEGRAM_SESSION)",
    )
    tg_login.add_argument(
        "--api-id",
        type=int,
        help="App api_id from my.telegram.org/apps (written to env)",
    )
    tg_login.add_argument(
        "--api-hash",
        help="App api_hash from my.telegram.org/apps (written to env)",
    )
    tg_login.add_argument(
        "--no-write-env",
        action="store_true",
        help="Do not write ~/.config/research-cli/env (print session JSON instead)",
    )
    tg_sub.add_parser(
        "me",
        help="Telegram user and/or tgstat.com cookie probe",
        parents=[shared],
    )
    tg_discover = tg_sub.add_parser(
        "discover",
        help="contacts.search: public users/groups/channels by name (no join)",
        parents=[shared],
    )
    tg_discover.add_argument("query", help="Name or username fragment")
    tg_discover.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    tg_history = tg_sub.add_parser(
        "history",
        help="Message history or in-chat search for a public @username (no join)",
        parents=[shared],
    )
    tg_history.add_argument("target", help="@username, t.me/user, or t.me/user/id")
    tg_history.add_argument("--search", help="Search inside this chat (messages.search)")
    tg_history.add_argument("--limit", type=int, default=50, help="Page size (default 50)")
    tg_history.add_argument("--offset-id", type=int, default=0, help="Pagination message id")
    tg_history.add_argument("--min-id", type=int, default=0, help="Only messages newer than this id")
    tg_resolve = tg_sub.add_parser(
        "resolve",
        help="Resolve @username or peek t.me/+invite (does not join)",
        parents=[shared],
    )
    tg_resolve.add_argument("target", help="@username, t.me/user, or t.me/+hash")
    tg_get = tg_sub.add_parser(
        "get",
        help="Fetch one message body (no file write)",
        parents=[shared],
    )
    tg_get.add_argument(
        "target",
        help="https://t.me/user/id, t.me/c/id/id, or joinchat/HASH/id",
    )
    tg_get.add_argument("--chat", help="@username when target is a bare message id")
    tg_download = tg_sub.add_parser(
        "download",
        help="Download media from one message (telegram.target from telegram search)",
        parents=[shared],
    )
    tg_download.add_argument(
        "target",
        help="https://t.me/user/id, t.me/c/id/id, joinchat/HASH/id, or numeric id (then --chat)",
    )
    tg_download.add_argument("--chat", help="@username or t.me/user when target is a bare id")
    tg_download.add_argument(
        "--output",
        "-o",
        help="File or directory (default: cwd, name from the document)",
    )
    help_p = sub.add_parser(
        "help",
        help="Print setup topics (install, keys)",
    )
    help_p.add_argument(
        "topic",
        nargs="?",
        default=None,
        metavar="TOPIC",
        help="install or keys (alias: installation). Omit to list topics.",
    )
    return parser


def _origin(args: argparse.Namespace, environ: Mapping[str, str], default: str) -> str:
    base_url = getattr(args, "base_url", None)
    if base_url:
        return base_url
    env_base = (environ.get("RESEARCH_CLI_BASE_URL") or "").strip()
    return env_base or default


def _timeout(args: argparse.Namespace) -> float:
    return float(getattr(args, "timeout", 60.0))


def _emit(
    payload: dict[str, Any], stdout: TextIO, *, compact: bool = False
) -> None:
    if compact:
        json.dump(payload, stdout, ensure_ascii=False, separators=(",", ":"))
    else:
        json.dump(payload, stdout, indent=2, ensure_ascii=False)
    stdout.write("\n")


def _dispatch_firecrawl(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, firecrawl.DEFAULT_ORIGIN)
    api_key = require_firecrawl_key(environ)
    if args.operation == "scrape":
        max_age = 0 if args.live else args.max_age
        only_main = False if args.no_main_content else None
        return firecrawl.scrape(
            args.url,
            api_key=api_key,
            formats=_csv(args.formats),
            only_main_content=only_main,
            max_age=max_age,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "search":
        return firecrawl.search(
            args.query,
            api_key=api_key,
            limit=args.limit,
            categories=_csv(args.categories),
            include_domains=_csv(args.include_domains),
            exclude_domains=_csv(args.exclude_domains),
            scrape=args.scrape,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "map":
        return firecrawl.map_site(
            args.url,
            api_key=api_key,
            search=args.search,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "papers":
        if args.papers_op == "search":
            return papers.search_papers(
                args.query,
                api_key=api_key,
                k=args.k,
                authors=args.authors,
                categories=args.categories,
                from_date=args.from_date,
                to_date=args.to_date,
                origin=origin,
                transport=transport,
                timeout=timeout,
            )
        if args.papers_op == "inspect":
            return papers.inspect_paper(
                args.paper_id,
                api_key=api_key,
                origin=origin,
                transport=transport,
                timeout=timeout,
            )
        if args.papers_op == "read":
            return papers.read_paper(
                args.paper_id,
                args.question,
                api_key=api_key,
                k=args.k,
                origin=origin,
                transport=transport,
                timeout=timeout,
            )
        if args.papers_op == "related":
            return papers.related_papers(
                args.paper_id,
                args.intent,
                api_key=api_key,
                mode=args.mode,
                k=args.k,
                anchors=_csv(args.anchors),
                origin=origin,
                transport=transport,
                timeout=timeout,
            )
    raise ValueError(f"unknown command: firecrawl {args.operation}")


def _dispatch_reddit(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, reddit.DEFAULT_ORIGIN)
    client_id, client_secret = require_reddit_credentials(environ)
    if args.operation == "search":
        return reddit.search(
            args.query,
            client_id=client_id,
            client_secret=client_secret,
            sort=args.sort,
            time=args.time,
            limit=args.limit,
            subreddit=args.subreddit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "thread":
        return reddit.thread(
            args.target,
            client_id=client_id,
            client_secret=client_secret,
            sort=args.sort,
            limit=args.limit,
            depth=args.depth,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "subreddit":
        return reddit.list_subreddit(
            args.name,
            client_id=client_id,
            client_secret=client_secret,
            sort=args.sort,
            time=args.time,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    raise ValueError(f"unknown command: reddit {args.operation}")


def _dispatch_sploitus(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, sploitus.DEFAULT_ORIGIN)
    if args.operation == "search":
        return sploitus.search(
            args.query,
            search_type=args.search_type,
            sort=args.sort,
            offset=args.offset,
            limit=args.limit,
            include_source=args.source,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "exploit":
        return sploitus.exploit(
            args.target,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "cve":
        return sploitus.cve(
            args.cve_id,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "product":
        return sploitus.product(
            args.name,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "latest":
        return sploitus.latest(
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "home":
        return sploitus.home(
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if args.operation == "autocomplete":
        return sploitus.autocomplete(
            args.query,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    raise ValueError(f"unknown command: sploitus {args.operation}")


def _dispatch_exploitdb(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, exploitdb.DEFAULT_ORIGIN)
    op = args.operation
    if op == "search":
        return exploitdb.search(
            args.query,
            search_type=args.search_type,
            platform=args.platform,
            port=args.port,
            cve=args.cve,
            text=args.text,
            author=args.author,
            tag=args.tag,
            verified=args.verified,
            hasapp=args.hasapp,
            nomsf=args.nomsf,
            offset=args.offset,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "latest":
        return exploitdb.latest(
            offset=args.offset,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "exploit":
        return exploitdb.exploit(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "raw":
        return exploitdb.raw(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "download":
        return exploitdb.download(
            args.target,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "papers":
        return exploitdb.papers(
            args.query,
            language=args.language,
            platform=args.platform,
            author=args.author,
            offset=args.offset,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "paper":
        return exploitdb.paper(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "shellcodes":
        return exploitdb.shellcodes(
            args.query,
            platform=args.platform,
            author=args.author,
            offset=args.offset,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "shellcode":
        return exploitdb.shellcode(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "ghdb":
        return exploitdb.ghdb(
            args.query,
            category=args.category,
            author=args.author,
            offset=args.offset,
            limit=args.limit,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "dork":
        return exploitdb.dork(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "authors":
        return exploitdb.authors(
            args.query, origin=origin, transport=transport, timeout=timeout
        )
    if op == "stats":
        return exploitdb.stats(origin=origin, transport=transport, timeout=timeout)
    raise ValueError(f"unknown command: exploitdb {args.operation}")


def _dispatch_malpedia(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, malpedia.DEFAULT_ORIGIN)
    op = args.operation
    if op == "search":
        return malpedia.search(
            args.query, origin=origin, transport=transport, timeout=timeout
        )
    if op == "family":
        return malpedia.family(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "actor":
        return malpedia.actor(
            args.target, origin=origin, transport=transport, timeout=timeout
        )
    if op == "yara":
        return malpedia.yara(
            args.target,
            as_zip=args.as_zip,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "families":
        return malpedia.families(
            limit=args.limit,
            full=args.full,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "actors":
        return malpedia.actors(
            limit=args.limit,
            full=args.full,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "bib":
        return malpedia.bib(
            family=args.family,
            actor=args.actor,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "misp":
        return malpedia.misp(
            output=args.output, origin=origin, transport=transport, timeout=timeout
        )
    if op == "references":
        return malpedia.references(
            url=args.url,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "yara-list":
        return malpedia.yara_list(
            family=args.family, origin=origin, transport=transport, timeout=timeout
        )
    if op == "yara-dump":
        return malpedia.yara_dump(
            tlp=args.tlp,
            auto=args.auto_rules,
            as_zip=args.as_zip,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "yara-after":
        return malpedia.yara_after(
            args.date,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
    if op == "version":
        return malpedia.version(origin=origin, transport=transport, timeout=timeout)
    raise ValueError(f"unknown command: malpedia {args.operation}")


def _dispatch_x(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    auth_token, ct0 = require_x_credentials(environ)
    origin = _origin(args, environ, x.DEFAULT_ORIGIN)
    fields = _csv(getattr(args, "fields", None))
    if args.operation == "search":
        return x.search(
            args.query,
            auth_token=auth_token,
            ct0=ct0,
            count=args.count,
            product=args.product,
            cursor=args.cursor,
            fields=fields,
            origin=origin,
            transport=transport,
            timeout=timeout,
            environ=environ,
        )
    if args.operation == "thread":
        return x.thread(
            args.target,
            auth_token=auth_token,
            ct0=ct0,
            cursor=args.cursor,
            fields=fields,
            origin=origin,
            transport=transport,
            timeout=timeout,
            environ=environ,
        )
    raise ValueError(f"unknown command: x {args.operation}")


def _dispatch_telegram(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    if args.operation in {
        "search",
        "sources",
        "mentions",
        "export",
        "catalogs",
    }:
        return _dispatch_telegram_index(args, environ, transport, timeout)
    if args.operation == "me":
        return _dispatch_telegram_me(args, environ, transport, timeout)
    if args.operation == "login":
        merged = dict(environ)
        api_id_flag = getattr(args, "api_id", None)
        api_hash_flag = (getattr(args, "api_hash", None) or "").strip()
        if api_id_flag is not None:
            merged["TELEGRAM_API_ID"] = str(api_id_flag)
        if api_hash_flag:
            merged["TELEGRAM_API_HASH"] = api_hash_flag
        api_id, api_hash = require_telegram_app(merged)
        session = (getattr(args, "session", None) or "").strip() or (
            optional_telegram_session(merged)
        )
        phone = (args.phone or merged.get("TELEGRAM_PHONE") or "").strip()
        code_hash = (
            getattr(args, "phone_code_hash", None)
            or merged.get("TELEGRAM_PHONE_CODE_HASH")
            or ""
        ).strip() or None
        env_path, session_file = telegram_persist_paths(
            merged, write=not getattr(args, "no_write_env", False)
        )
        return telegram.login(
            phone=phone,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            code=args.code,
            phone_code_hash=code_hash,
            password=args.password,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    api_id, api_hash = require_telegram_app(environ)
    session = require_telegram_session(environ)
    env_path, session_file = telegram_persist_paths(environ)
    if args.operation == "discover":
        return telegram.discover(
            args.query,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            limit=args.limit,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    if args.operation == "history":
        return telegram.history(
            args.target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            search_query=args.search,
            limit=args.limit,
            offset_id=args.offset_id,
            min_id=args.min_id,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    if args.operation == "resolve":
        return telegram.resolve(
            args.target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    if args.operation == "get":
        return telegram.get(
            args.target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            chat=getattr(args, "chat", None),
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    if args.operation == "download":
        return telegram.download(
            args.target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            chat=args.chat,
            output=args.output,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    raise ValueError(f"unknown command: telegram {args.operation}")


def _telegram_get_fn(
    environ: Mapping[str, str], timeout: float
) -> Any:
    api_id, api_hash = require_telegram_app(environ)
    session = require_telegram_session(environ)
    env_path, session_file = telegram_persist_paths(environ)

    def _go(target: str) -> dict[str, Any]:
        return telegram.get(
            target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )

    return _go


def _telegram_download_fn(
    environ: Mapping[str, str], timeout: float
) -> Any:
    api_id, api_hash = require_telegram_app(environ)
    session = require_telegram_session(environ)
    env_path, session_file = telegram_persist_paths(environ)

    def _go(target: str, output: str | None) -> dict[str, Any]:
        return telegram.download(
            target,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            output=output,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )

    return _go


def _telegram_get_many_fn(
    environ: Mapping[str, str], timeout: float
) -> Any:
    api_id, api_hash = require_telegram_app(environ)
    session = require_telegram_session(environ)
    env_path, session_file = telegram_persist_paths(environ)

    def _go(targets: list[str], jobs: int = 4) -> list[dict[str, Any]]:
        return telegram.get_many(
            targets,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            jobs=jobs,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )

    return _go


def _telegram_download_many_fn(
    environ: Mapping[str, str], timeout: float
) -> Any:
    api_id, api_hash = require_telegram_app(environ)
    session = require_telegram_session(environ)
    env_path, session_file = telegram_persist_paths(environ)

    def _go(
        items: list[tuple[str, str | None]], jobs: int = 4
    ) -> list[dict[str, Any]]:
        return telegram.download_many(
            items,
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            jobs=jobs,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )

    return _go


def _telegram_ready(environ: Mapping[str, str]) -> bool:
    try:
        require_telegram_app(environ)
        require_telegram_session(environ)
        return True
    except MissingKeyError:
        return False


def _dispatch_telegram_me(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    if _telegram_ready(environ):
        api_id, api_hash = require_telegram_app(environ)
        session = require_telegram_session(environ)
        env_path, session_file = telegram_persist_paths(environ)
        payload = telegram.me(
            api_id=api_id,
            api_hash=api_hash,
            session=session,
            timeout=timeout,
            env_path=env_path,
            session_file=session_file,
        )
    cookie = optional_tgstat_session(environ)
    if cookie:
        origin = _origin(args, environ, tgstat.DEFAULT_ORIGIN)
        probe = tgstat.me(
            cookie=cookie,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
        if payload is None:
            payload = {"provider": "telegram", "operation": "me"}
        payload["tgstat"] = {"status": probe.get("status", "ok")}
    if payload is None:
        raise MissingKeyError(
            "telegram",
            ("TELEGRAM_SESSION", "TGSTAT_IDR", "TGSTAT_SIRK"),
            detail=(
                "telegram me needs TELEGRAM_SESSION (Telegram user) and/or "
                "TGSTAT_IDR+TGSTAT_SIRK (tgstat.com cookies for telegram search)"
            ),
        )
    return payload


def _dispatch_telegram_index(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any]:
    origin = _origin(args, environ, tgstat.DEFAULT_ORIGIN)
    if args.operation == "catalogs":
        return tgstat.catalogs()
    cookie = require_tgstat_session(environ)
    filters = _tgstat_filter_kwargs(args)
    if args.operation == "search":
        include_private = bool(getattr(args, "private", False))
        payload = tgstat.search(
            args.query,
            cookie=cookie,
            limit=args.limit,
            offset=args.offset,
            include_private=include_private,
            origin=origin,
            transport=transport,
            timeout=timeout,
            **filters,
        )
        download_dir = getattr(args, "download", None)
        media = getattr(args, "media", None)
        if download_dir or media:
            results = payload.get("results") or []
            tgstat.fetch_files(
                results,
                get_many=_telegram_get_many_fn(environ, timeout),
                download_many=(
                    _telegram_download_many_fn(environ, timeout)
                    if download_dir
                    else None
                ),
                output=download_dir,
                media=media,
                include_private=include_private,
                allow_large=bool(getattr(args, "allow_large", False)),
                jobs=int(getattr(args, "jobs", tgstat.DOWNLOAD_JOBS) or tgstat.DOWNLOAD_JOBS),
            )
            if media:
                kept = []
                for hit in results:
                    kind = (hit.get("telegram") or {}).get("media")
                    if isinstance(kind, dict):
                        kind = kind.get("type")
                    if kind == media:
                        kept.append(hit)
                payload["results"] = kept
            payload["count"] = len(payload.get("results") or [])
        return payload
    if args.operation == "sources":
        return tgstat.sources(
            args.query,
            cookie=cookie,
            origin=origin,
            transport=transport,
            timeout=timeout,
            **filters,
        )
    if args.operation == "mentions":
        return tgstat.mentions(
            args.query,
            cookie=cookie,
            group=args.group,
            origin=origin,
            transport=transport,
            timeout=timeout,
            **filters,
        )
    if args.operation == "export":
        return tgstat.export(
            args.query,
            cookie=cookie,
            output=args.output,
            origin=origin,
            transport=transport,
            timeout=timeout,
            **filters,
        )
    raise ValueError(f"unknown command: telegram {args.operation}")


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
    if args.provider == "brave" and args.operation == "search":
        return brave.web_search(
            args.query,
            api_key=require_brave_key(environ),
            count=args.count,
            country=args.country,
            freshness=args.freshness,
            offset=args.offset,
            origin=_origin(args, environ, brave.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "brave" and args.operation == "llm-context":
        return brave.llm_context(
            args.query,
            api_key=require_brave_key(environ),
            count=args.count,
            country=args.country,
            freshness=args.freshness,
            origin=_origin(args, environ, brave.DEFAULT_ORIGIN),
            transport=transport,
            timeout=timeout,
        )
    if args.provider == "exa" and args.operation == "search":
        return exa.search(
            args.query,
            api_key=require_exa_key(environ),
            num_results=args.num_results,
            include_domains=_csv(args.include_domains),
            exclude_domains=_csv(args.exclude_domains),
            category=args.category,
            start_published=args.start_published,
            end_published=args.end_published,
            highlights=args.highlights,
            text=args.text,
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
    if args.provider == "firecrawl":
        return _dispatch_firecrawl(args, environ, transport, timeout)
    if args.provider == "reddit":
        return _dispatch_reddit(args, environ, transport, timeout)
    if args.provider == "sploitus":
        return _dispatch_sploitus(args, environ, transport, timeout)
    if args.provider == "exploitdb":
        return _dispatch_exploitdb(args, environ, transport, timeout)
    if args.provider == "malpedia":
        return _dispatch_malpedia(args, environ, transport, timeout)
    if args.provider == "x":
        return _dispatch_x(args, environ, transport, timeout)
    if args.provider == "telegram":
        return _dispatch_telegram(args, environ, transport, timeout)
    if args.provider == "help":
        return help_topic_payload(getattr(args, "topic", None))
    raise ValueError(f"unknown command: {args.provider} {getattr(args, 'operation', '')}")


def _schedule_update(
    environ: Mapping[str, str],
    spawn_update: Callable[[Mapping[str, str]], None] | None,
) -> None:
    try:
        if spawn_update is not None:
            spawn_update(environ)
            return
        spawn_background_update(environ=environ)
    except Exception:
        return


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    spawn_update: Callable[[Mapping[str, str]], None] | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = load_provider_keys(os.environ) if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    if "--self-update" in argv:
        try:
            payload = run_self_update(environ=environ, transport=transport)
        except UpdateError as exc:
            print(f"error: {exc}", file=stderr)
            return 1
        _emit(payload, stdout)
        return 0
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = 0 if exc.code is None else int(exc.code)
        _schedule_update(environ, spawn_update)
        return code
    code = 0
    try:
        result = _dispatch(args, environ, transport)
    except MissingKeyError as exc:
        print(f"error: {exc}", file=stderr)
        print(f"write keys to {default_env_path(environ)}", file=stderr)
        code = 2
    except ProviderHttpError as exc:
        print(f"error: {exc}", file=stderr)
        code = 1
    else:
        _emit(
            result,
            stdout,
            compact=bool(getattr(args, "compact", False)),
        )
        try:
            stdout.flush()
        except Exception:
            pass
    _schedule_update(environ, spawn_update)
    return code


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
