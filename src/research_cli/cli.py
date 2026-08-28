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
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
    require_reddit_credentials,
)
from research_cli.providers import bgpt, brave, exa, exploitdb, firecrawl, malpedia, reddit, sploitus
from research_cli.providers import firecrawl_papers as papers
from research_cli.update import run_self_update, spawn_background_update

DESCRIPTION = (
    "Agent-facing research CLI. Direct HTTP REST calls for bgpt paper search, "
    "brave search / llm-context, exa search/contents, firecrawl "
    "scrape/search/map/papers, reddit search/thread/subreddit, sploitus "
    "exploit/hacktool search, exploit-db exploits/GHDB/papers/shellcodes, "
    "and malpedia malware families/actors/YARA/bib/MISP (guest). "
    "Do not use MCP; run this CLI."
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

examples:
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
"""


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


def build_parser() -> argparse.ArgumentParser:
    shared = _shared_flags()
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
        _emit(result, stdout)
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
