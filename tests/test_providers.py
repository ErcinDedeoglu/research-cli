from __future__ import annotations

import base64
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.errors import ProviderHttpError  # noqa: E402
from research_cli.http import HttpResponse  # noqa: E402
from research_cli.providers import bgpt, brave, exa, exploitdb, firecrawl, malpedia, reddit, sploitus, x  # noqa: E402
from research_cli.providers import x_transaction  # noqa: E402

from research_cli.providers import firecrawl_papers as papers  # noqa: E402

from fixtures import (  # noqa: E402
    BGPT_DOI,
    BGPT_PAYLOAD,
    BGPT_TITLE,
    BRAVE_LLM_PAYLOAD,
    BRAVE_LLM_TEXT,
    BRAVE_LLM_TITLE,
    BRAVE_LLM_URL,
    BRAVE_PAYLOAD,
    BRAVE_TITLE,
    BRAVE_URL,
    EXA_CONTENTS_PAYLOAD,
    EXA_CONTENTS_TEXT,
    EXA_CONTENTS_TITLE,
    EXA_CONTENTS_URL,
    EXA_SEARCH_PAYLOAD,
    EXA_SEARCH_TITLE,
    EXA_SEARCH_URL,
    FIRECRAWL_MAP_PAYLOAD,
    FIRECRAWL_MAP_TITLE,
    FIRECRAWL_MAP_URL,
    FIRECRAWL_SCRAPE_MD,
    FIRECRAWL_SCRAPE_PAYLOAD,
    FIRECRAWL_SCRAPE_TITLE,
    FIRECRAWL_SCRAPE_URL,
    FIRECRAWL_SEARCH_PAYLOAD,
    FIRECRAWL_SEARCH_SNIPPET,
    FIRECRAWL_SEARCH_TITLE,
    FIRECRAWL_SEARCH_URL,
    PAPER_ID,
    PAPER_PASSAGE,
    PAPER_TITLE,
    PAPERS_INSPECT_PAYLOAD,
    PAPERS_READ_PAYLOAD,
    PAPERS_RELATED_PAYLOAD,
    PAPERS_RELATED_TITLE,
    PAPERS_SEARCH_PAYLOAD,
    REDDIT_COMMENT_BODY,
    REDDIT_LINK_URL,
    REDDIT_POST_ID,
    REDDIT_REPLY_BODY,
    REDDIT_SEARCH_PAYLOAD,
    REDDIT_SELFTEXT,
    REDDIT_THREAD_PAYLOAD,
    REDDIT_TITLE,
    REDDIT_TOKEN,
    REDDIT_TOKEN_PAYLOAD,
    REDDIT_URL,
    SPLOITUS_AUTOCOMPLETE,
    SPLOITUS_CVE,
    SPLOITUS_CVE_HTML,
    SPLOITUS_EXPLOIT_HTML,
    SPLOITUS_HOME_HTML,
    SPLOITUS_HREF,
    SPLOITUS_ID,
    SPLOITUS_LATEST_HTML,
    SPLOITUS_PRODUCT_HTML,
    SPLOITUS_PRODUCT_PAGE2_HTML,
    SPLOITUS_SEARCH_PAYLOAD,
    SPLOITUS_SOURCE,
    SPLOITUS_TITLE,
    SPLOITUS_TOOL_ID,
    SPLOITUS_TOOL_PAYLOAD,
    SPLOITUS_TOOL_TITLE,
    EDB_AUTHOR_NAME,
    EDB_AUTHOR_PAYLOAD,
    EDB_AUTHORS_PAYLOAD,
    EDB_DORK_HTML,
    EDB_DORK_ID,
    EDB_DORK_TITLE,
    EDB_EXPLOIT_HTML,
    EDB_GHDB_PAYLOAD,
    EDB_ID,
    EDB_LATEST_PAYLOAD,
    EDB_PAPER_HTML,
    EDB_PAPER_ID,
    EDB_PAPER_TITLE,
    EDB_PAPERS_PAYLOAD,
    EDB_SEARCH_PAYLOAD,
    EDB_SHELLCODE_HTML,
    EDB_SHELLCODE_ID,
    EDB_SHELLCODE_TITLE,
    EDB_SHELLCODES_PAYLOAD,
    EDB_SOURCE,
    EDB_TITLE,
    MALPEDIA_ACTOR_ID,
    MALPEDIA_ACTOR_PAYLOAD,
    MALPEDIA_ACTORS,
    MALPEDIA_ACTORS_FULL,
    MALPEDIA_BIB,
    MALPEDIA_FAMILIES,
    MALPEDIA_FAMILIES_FULL,
    MALPEDIA_FAMILY_ID,
    MALPEDIA_FAMILY_PAYLOAD,
    MALPEDIA_FIND_ACTOR,
    MALPEDIA_FIND_FAMILY,
    MALPEDIA_HASH,
    MALPEDIA_MISP,
    MALPEDIA_REF_URL,
    MALPEDIA_REFERENCES,
    MALPEDIA_SAMPLE_INFO,
    MALPEDIA_SAMPLES_PAYLOAD,
    MALPEDIA_VERSION_PAYLOAD,
    MALPEDIA_YARA_LIST,
    MALPEDIA_YARA_NAME,
    MALPEDIA_YARA_PAYLOAD,
    MALPEDIA_YARA_RAW,
    MALPEDIA_YARA_SOURCE,
    MALPEDIA_ZIP,
    X_CURSOR,
    X_HOME_HTML,
    X_MAIN_JS,
    X_ONDEMAND_HASH,
    X_ONDEMAND_JS,
    X_QUERY_DETAIL,
    X_QUERY_SEARCH,
    X_SEARCH_PAYLOAD,
    X_TEXT,
    X_THREAD_PAYLOAD,
    X_TWEET_ID,
    X_TWEET_RESULT,
    X_USER,
    X_VERIFY_KEY,
)


class CapturingTransport:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.request = None

    def __call__(self, request):
        self.request = request
        body = json.dumps(self.payload).encode("utf-8")
        return HttpResponse(
            status=self.status,
            headers={"Content-Type": "application/json"},
            body=body,
        )


class HtmlTransport:
    def __init__(self, *pages: str) -> None:
        self.pages = list(pages)
        self.requests: list = []
        self.request = None

    def __call__(self, request):
        self.requests.append(request)
        self.request = request
        body = (self.pages.pop(0) if self.pages else "").encode("utf-8")
        return HttpResponse(
            status=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            body=body,
        )


class SequentialTransport:
    def __init__(self, *payloads: object) -> None:
        self.payloads = list(payloads)
        self.requests: list = []

    def __call__(self, request):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        body = json.dumps(payload).encode("utf-8")
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=body,
        )


class ScriptedTransport:
    def __init__(self, *items: object) -> None:
        self.items = list(items)
        self.requests: list = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.items.pop(0)
        if isinstance(item, HttpResponse):
            return item
        if isinstance(item, (bytes, bytearray)):
            return HttpResponse(status=200, headers={}, body=bytes(item))
        if isinstance(item, str):
            return HttpResponse(
                status=200,
                headers={"Content-Type": "text/plain; charset=UTF-8"},
                body=item.encode("utf-8"),
            )
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(item).encode("utf-8"),
        )


class ProviderClientTests(unittest.TestCase):
    def test_bgpt_search_post_path_and_paper_fields(self) -> None:
        transport = CapturingTransport(BGPT_PAYLOAD)
        out = bgpt.search_papers("CRISPR delivery", transport=transport)
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "bgpt.pro")
        self.assertEqual(parsed.path, "/api/mcp-search")
        self.assertEqual(req.headers.get("Content-Type"), "application/json")
        body = json.loads(req.body.decode("utf-8"))
        self.assertEqual(body["query"], "CRISPR delivery")
        self.assertEqual(out["results"][0]["title"], BGPT_TITLE)
        self.assertEqual(out["results"][0]["doi"], BGPT_DOI)

    def test_bgpt_http_error_includes_body(self) -> None:
        transport = CapturingTransport({"error": "quota exceeded"}, status=402)
        with self.assertRaises(ProviderHttpError) as ctx:
            bgpt.search_papers("q", transport=transport)
        message = str(ctx.exception).lower()
        self.assertIn("bgpt", message)
        self.assertIn("quota exceeded", message)

    def test_brave_search_get_token_and_hits(self) -> None:
        transport = CapturingTransport(BRAVE_PAYLOAD)
        out = brave.web_search(
            "rust async", api_key="test-brave-key", transport=transport
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "GET")
        self.assertEqual(parsed.hostname, "api.search.brave.com")
        self.assertEqual(parsed.path, "/res/v1/web/search")
        self.assertEqual(req.headers.get("X-Subscription-Token"), "test-brave-key")
        self.assertEqual(parse_qs(parsed.query)["q"], ["rust async"])
        self.assertEqual(out["results"][0]["title"], BRAVE_TITLE)
        self.assertEqual(out["results"][0]["url"], BRAVE_URL)

    def test_brave_search_forwards_freshness_and_country(self) -> None:
        transport = CapturingTransport(BRAVE_PAYLOAD)
        brave.web_search(
            "q",
            api_key="k",
            country="GB",
            freshness="pw",
            offset=1,
            transport=transport,
        )
        query = parse_qs(urlparse(transport.request.url).query)
        self.assertEqual(query["country"], ["GB"])
        self.assertEqual(query["freshness"], ["pw"])
        self.assertEqual(query["offset"], ["1"])

    def test_brave_llm_context_get_path_and_snippets(self) -> None:
        transport = CapturingTransport(BRAVE_LLM_PAYLOAD)
        out = brave.llm_context("RAG", api_key="test-brave-key", transport=transport)
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "GET")
        self.assertEqual(parsed.hostname, "api.search.brave.com")
        self.assertEqual(parsed.path, "/res/v1/llm/context")
        self.assertEqual(req.headers.get("X-Subscription-Token"), "test-brave-key")
        hit = out["results"][0]
        self.assertEqual(hit["title"], BRAVE_LLM_TITLE)
        self.assertEqual(hit["url"], BRAVE_LLM_URL)
        self.assertEqual(hit["text"], BRAVE_LLM_TEXT)

    def test_exa_search_post_api_key_and_hits(self) -> None:
        transport = CapturingTransport(EXA_SEARCH_PAYLOAD)
        out = exa.search("llm evals", api_key="test-exa-key", transport=transport)
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "api.exa.ai")
        self.assertEqual(parsed.path, "/search")
        self.assertEqual(req.headers.get("x-api-key"), "test-exa-key")
        self.assertEqual(out["results"][0]["title"], EXA_SEARCH_TITLE)
        self.assertEqual(out["results"][0]["url"], EXA_SEARCH_URL)

    def test_exa_search_includes_filters_and_contents_flags(self) -> None:
        transport = CapturingTransport(EXA_SEARCH_PAYLOAD)
        exa.search(
            "llm evals",
            api_key="test-exa-key",
            include_domains=["arxiv.org"],
            category="research paper",
            start_published="2025-01-01",
            highlights=True,
            transport=transport,
        )
        body = json.loads(transport.request.body.decode("utf-8"))
        self.assertEqual(body["includeDomains"], ["arxiv.org"])
        self.assertEqual(body["category"], "research paper")
        self.assertEqual(body["startPublishedDate"], "2025-01-01")
        self.assertEqual(body["contents"], {"highlights": True})

    def test_exa_contents_post_text_or_highlights(self) -> None:
        transport = CapturingTransport(EXA_CONTENTS_PAYLOAD)
        out = exa.contents(
            EXA_CONTENTS_URL, api_key="test-exa-key", transport=transport
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "api.exa.ai")
        self.assertEqual(parsed.path, "/contents")
        self.assertEqual(req.headers.get("x-api-key"), "test-exa-key")
        page = out["results"][0]
        self.assertEqual(page["title"], EXA_CONTENTS_TITLE)
        self.assertEqual(page["url"], EXA_CONTENTS_URL)
        self.assertEqual(page["text"], EXA_CONTENTS_TEXT)
        self.assertTrue(page.get("highlights"))

    def test_firecrawl_scrape_bearer_and_markdown(self) -> None:
        transport = CapturingTransport(FIRECRAWL_SCRAPE_PAYLOAD)
        out = firecrawl.scrape(
            FIRECRAWL_SCRAPE_URL,
            api_key="test-firecrawl-key",
            transport=transport,
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "api.firecrawl.dev")
        self.assertEqual(parsed.path, "/v2/scrape")
        self.assertEqual(
            req.headers.get("Authorization"), "Bearer test-firecrawl-key"
        )
        page = out["results"][0]
        self.assertEqual(page["title"], FIRECRAWL_SCRAPE_TITLE)
        self.assertEqual(page["url"], FIRECRAWL_SCRAPE_URL)
        self.assertEqual(page["markdown"], FIRECRAWL_SCRAPE_MD)

    def test_firecrawl_scrape_live_sets_max_age_zero(self) -> None:
        transport = CapturingTransport(FIRECRAWL_SCRAPE_PAYLOAD)
        firecrawl.scrape(
            FIRECRAWL_SCRAPE_URL,
            api_key="k",
            max_age=0,
            formats=["markdown", "html"],
            only_main_content=False,
            transport=transport,
        )
        body = json.loads(transport.request.body.decode("utf-8"))
        self.assertEqual(body["maxAge"], 0)
        self.assertEqual(body["formats"], ["markdown", "html"])
        self.assertIs(body["onlyMainContent"], False)

    def test_firecrawl_search_bearer_url_and_title(self) -> None:
        transport = CapturingTransport(FIRECRAWL_SEARCH_PAYLOAD)
        out = firecrawl.search(
            "web scraping python",
            api_key="test-firecrawl-key",
            transport=transport,
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "api.firecrawl.dev")
        self.assertEqual(parsed.path, "/v2/search")
        self.assertEqual(
            req.headers.get("Authorization"), "Bearer test-firecrawl-key"
        )
        hit = out["results"][0]
        self.assertEqual(hit["url"], FIRECRAWL_SEARCH_URL)
        self.assertEqual(hit["title"], FIRECRAWL_SEARCH_TITLE)
        self.assertEqual(hit["snippet"], FIRECRAWL_SEARCH_SNIPPET)

    def test_firecrawl_search_categories_and_scrape_options(self) -> None:
        transport = CapturingTransport(FIRECRAWL_SEARCH_PAYLOAD)
        firecrawl.search(
            "q",
            api_key="k",
            categories=["research"],
            include_domains=["arxiv.org"],
            scrape=True,
            transport=transport,
        )
        body = json.loads(transport.request.body.decode("utf-8"))
        self.assertEqual(body["categories"], ["research"])
        self.assertEqual(body["includeDomains"], ["arxiv.org"])
        self.assertEqual(body["scrapeOptions"], {"formats": ["markdown"]})

    def test_firecrawl_map_post_path_and_links(self) -> None:
        transport = CapturingTransport(FIRECRAWL_MAP_PAYLOAD)
        out = firecrawl.map_site(
            "https://docs.firecrawl.dev",
            api_key="test-firecrawl-key",
            search="webhook",
            transport=transport,
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "api.firecrawl.dev")
        self.assertEqual(parsed.path, "/v2/map")
        self.assertEqual(
            req.headers.get("Authorization"), "Bearer test-firecrawl-key"
        )
        body = json.loads(req.body.decode("utf-8"))
        self.assertEqual(body["search"], "webhook")
        self.assertEqual(out["results"][0]["url"], FIRECRAWL_MAP_URL)
        self.assertEqual(out["results"][0]["title"], FIRECRAWL_MAP_TITLE)

    def test_firecrawl_papers_search_get_and_title(self) -> None:
        transport = CapturingTransport(PAPERS_SEARCH_PAYLOAD)
        out = papers.search_papers(
            "diffusion", api_key="test-firecrawl-key", transport=transport
        )
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "GET")
        self.assertEqual(parsed.path, "/v2/search/research/papers")
        self.assertEqual(parse_qs(parsed.query)["query"], ["diffusion"])
        self.assertEqual(out["results"][0]["title"], PAPER_TITLE)
        self.assertEqual(out["results"][0]["primaryId"], PAPER_ID)

    def test_firecrawl_papers_inspect_read_related(self) -> None:
        inspect_t = CapturingTransport(PAPERS_INSPECT_PAYLOAD)
        inspected = papers.inspect_paper(
            PAPER_ID, api_key="k", transport=inspect_t
        )
        self.assertIn("/v2/search/research/papers/arxiv%3A2105.05233", inspect_t.request.url)
        self.assertEqual(inspected["results"][0]["title"], PAPER_TITLE)

        read_t = CapturingTransport(PAPERS_READ_PAYLOAD)
        read = papers.read_paper(
            PAPER_ID, "what is the architecture?", api_key="k", transport=read_t
        )
        self.assertEqual(parse_qs(urlparse(read_t.request.url).query)["query"], ["what is the architecture?"])
        self.assertEqual(read["results"][0]["text"], PAPER_PASSAGE)

        related_t = CapturingTransport(PAPERS_RELATED_PAYLOAD)
        related = papers.related_papers(
            PAPER_ID, "efficient attention", api_key="k", transport=related_t
        )
        parsed = urlparse(related_t.request.url)
        self.assertTrue(parsed.path.endswith("/similar"))
        self.assertEqual(parse_qs(parsed.query)["intent"], ["efficient attention"])
        self.assertEqual(related["results"][0]["title"], PAPERS_RELATED_TITLE)

    def test_reddit_search_token_then_listing(self) -> None:
        transport = SequentialTransport(REDDIT_TOKEN_PAYLOAD, REDDIT_SEARCH_PAYLOAD)
        out = reddit.search(
            "python tutorial",
            client_id="cid",
            client_secret="csecret",
            transport=transport,
        )
        self.assertEqual(len(transport.requests), 2)
        token_req = transport.requests[0]
        token_parsed = urlparse(token_req.url)
        self.assertEqual(token_req.method, "POST")
        self.assertEqual(token_parsed.hostname, "www.reddit.com")
        self.assertEqual(token_parsed.path, "/api/v1/access_token")
        self.assertEqual(
            token_req.headers.get("Content-Type"),
            "application/x-www-form-urlencoded",
        )
        self.assertTrue(
            token_req.headers.get("Authorization", "").startswith("Basic ")
        )
        self.assertEqual(token_req.body, b"grant_type=client_credentials")
        search_req = transport.requests[1]
        search_parsed = urlparse(search_req.url)
        self.assertEqual(search_req.method, "GET")
        self.assertEqual(search_parsed.hostname, "oauth.reddit.com")
        self.assertEqual(search_parsed.path, "/search")
        self.assertEqual(
            search_req.headers.get("Authorization"), f"Bearer {REDDIT_TOKEN}"
        )
        query = parse_qs(search_parsed.query)
        self.assertEqual(query["q"], ["python tutorial"])
        self.assertEqual(query["sort"], ["relevance"])
        self.assertEqual(query["t"], ["all"])
        hit = out["results"][0]
        self.assertEqual(hit["title"], REDDIT_TITLE)
        self.assertEqual(hit["url"], REDDIT_URL)
        self.assertEqual(hit["link_url"], REDDIT_LINK_URL)
        self.assertEqual(hit["subreddit"], "python")
        self.assertEqual(hit["description"], REDDIT_SELFTEXT)

    def test_reddit_search_subreddit_path_and_filters(self) -> None:
        transport = SequentialTransport(REDDIT_TOKEN_PAYLOAD, REDDIT_SEARCH_PAYLOAD)
        reddit.search(
            "pandas",
            client_id="cid",
            client_secret="csecret",
            sort="top",
            time="week",
            limit=10,
            subreddit="r/python",
            transport=transport,
        )
        parsed = urlparse(transport.requests[1].url)
        self.assertEqual(parsed.path, "/r/python/search")
        query = parse_qs(parsed.query)
        self.assertEqual(query["q"], ["pandas"])
        self.assertEqual(query["sort"], ["top"])
        self.assertEqual(query["t"], ["week"])
        self.assertEqual(query["limit"], ["10"])
        self.assertEqual(query["restrict_sr"], ["true"])

    def test_reddit_fixture_origin_uses_same_host_for_token(self) -> None:
        transport = SequentialTransport(REDDIT_TOKEN_PAYLOAD, REDDIT_SEARCH_PAYLOAD)
        reddit.search(
            "q",
            client_id="cid",
            client_secret="csecret",
            origin="http://127.0.0.1:9",
            transport=transport,
        )
        self.assertEqual(
            urlparse(transport.requests[0].url).hostname, "127.0.0.1"
        )
        self.assertEqual(
            urlparse(transport.requests[1].url).hostname, "127.0.0.1"
        )

    def test_reddit_thread_comments_path_and_nested_bodies(self) -> None:
        transport = SequentialTransport(REDDIT_TOKEN_PAYLOAD, REDDIT_THREAD_PAYLOAD)
        out = reddit.thread(
            "https://www.reddit.com/r/python/comments/abc123/fixture_post/",
            client_id="cid",
            client_secret="csecret",
            sort="top",
            limit=50,
            transport=transport,
        )
        parsed = urlparse(transport.requests[1].url)
        self.assertEqual(transport.requests[1].method, "GET")
        self.assertEqual(parsed.path, f"/comments/{REDDIT_POST_ID}")
        query = parse_qs(parsed.query)
        self.assertEqual(query["sort"], ["top"])
        self.assertEqual(query["limit"], ["50"])
        hit = out["results"][0]
        self.assertEqual(hit["id"], REDDIT_POST_ID)
        self.assertEqual(hit["title"], REDDIT_TITLE)
        self.assertEqual(hit["comments"][0]["body"], REDDIT_COMMENT_BODY)
        self.assertEqual(hit["comments"][0]["depth"], 0)
        self.assertEqual(hit["comments"][1]["body"], REDDIT_REPLY_BODY)
        self.assertEqual(hit["comments"][1]["depth"], 1)

    def test_reddit_thread_accepts_bare_and_t3_ids(self) -> None:
        for target in ("abc123", "t3_abc123"):
            transport = SequentialTransport(
                REDDIT_TOKEN_PAYLOAD, REDDIT_THREAD_PAYLOAD
            )
            reddit.thread(
                target,
                client_id="cid",
                client_secret="csecret",
                transport=transport,
            )
            self.assertEqual(
                urlparse(transport.requests[1].url).path, "/comments/abc123"
            )

    def test_reddit_subreddit_listing_path_and_time(self) -> None:
        transport = SequentialTransport(REDDIT_TOKEN_PAYLOAD, REDDIT_SEARCH_PAYLOAD)
        out = reddit.list_subreddit(
            "r/python",
            client_id="cid",
            client_secret="csecret",
            sort="top",
            time="week",
            limit=10,
            transport=transport,
        )
        parsed = urlparse(transport.requests[1].url)
        self.assertEqual(parsed.path, "/r/python/top")
        query = parse_qs(parsed.query)
        self.assertEqual(query["t"], ["week"])
        self.assertEqual(query["limit"], ["10"])
        self.assertEqual(out["operation"], "subreddit")
        self.assertEqual(out["subreddit"], "python")
        self.assertEqual(out["results"][0]["title"], REDDIT_TITLE)

    def test_sploitus_search_post_frontend_header_and_body(self) -> None:
        transport = CapturingTransport(SPLOITUS_SEARCH_PAYLOAD)
        out = sploitus.search("log4j rce", transport=transport)
        req = transport.request
        parsed = urlparse(req.url)
        self.assertEqual(req.method, "POST")
        self.assertEqual(parsed.hostname, "sploitus.com")
        self.assertEqual(parsed.path, "/search")
        self.assertEqual(req.headers.get("X-Requested-With"), "sploitus-frontend")
        self.assertEqual(req.headers.get("Content-Type"), "application/json")
        self.assertEqual(req.headers.get("Accept"), "application/json")
        self.assertEqual(req.headers.get("Referer"), "https://sploitus.com/")
        body = json.loads(req.body.decode("utf-8"))
        self.assertEqual(
            body,
            {
                "type": "exploits",
                "sort": "default",
                "query": "log4j rce",
                "offset": 0,
            },
        )
        self.assertEqual(set(body), {"type", "sort", "query", "offset"})
        self.assertEqual(out["provider"], "sploitus")
        self.assertEqual(out["operation"], "search")
        self.assertEqual(out["type"], "exploits")
        self.assertEqual(out["total"], 42)
        hit = out["results"][0]
        self.assertEqual(hit["id"], SPLOITUS_ID)
        self.assertEqual(hit["title"], SPLOITUS_TITLE)
        self.assertEqual(hit["href"], SPLOITUS_HREF)
        self.assertEqual(hit["url"], f"https://sploitus.com/exploit?id={SPLOITUS_ID}")
        self.assertEqual(hit["cve"], [SPLOITUS_CVE])
        self.assertEqual(hit["epss"], 0.99)
        self.assertNotIn("source", hit)

    def test_sploitus_search_source_flag_and_tools_type(self) -> None:
        sourced = sploitus.search(
            "log4j",
            include_source=True,
            transport=CapturingTransport(SPLOITUS_SEARCH_PAYLOAD),
        )
        self.assertEqual(sourced["results"][0]["source"], SPLOITUS_SOURCE)
        transport = CapturingTransport(SPLOITUS_TOOL_PAYLOAD)
        out = sploitus.search(
            "c2", search_type="tools", sort="date", offset=10, transport=transport
        )
        body = json.loads(transport.request.body.decode("utf-8"))
        self.assertEqual(body["type"], "tools")
        self.assertEqual(body["sort"], "date")
        self.assertEqual(body["offset"], 10)
        rel = CapturingTransport(SPLOITUS_SEARCH_PAYLOAD)
        sploitus.search("q", sort="relevance", transport=rel)
        self.assertEqual(
            json.loads(rel.request.body.decode("utf-8"))["sort"], "default"
        )
        cvss = CapturingTransport(SPLOITUS_SEARCH_PAYLOAD)
        sploitus.search("q", sort="cvss", transport=cvss)
        self.assertEqual(
            json.loads(cvss.request.body.decode("utf-8"))["sort"], "score"
        )
        hit = out["results"][0]
        self.assertEqual(hit["id"], SPLOITUS_TOOL_ID)
        self.assertEqual(hit["title"], SPLOITUS_TOOL_TITLE)
        self.assertEqual(hit["download"], "https://kitploit.example/c2.zip")
        self.assertEqual(out["type"], "tools")

    def test_sploitus_search_paginates_offset_by_page_length(self) -> None:
        page1 = {
            "exploits": [
                {"id": f"E-{i}", "title": f"Hit {i}", "href": f"https://ex/{i}"}
                for i in range(10)
            ],
            "exploits_total": 15,
        }
        page2 = {
            "exploits": [
                {"id": f"E-{i}", "title": f"Hit {i}", "href": f"https://ex/{i}"}
                for i in range(10, 15)
            ],
            "exploits_total": 15,
        }
        transport = SequentialTransport(page1, page2)
        out = sploitus.search("q", limit=12, transport=transport)
        self.assertEqual(len(transport.requests), 2)
        first = json.loads(transport.requests[0].body.decode("utf-8"))
        second = json.loads(transport.requests[1].body.decode("utf-8"))
        self.assertEqual(first["offset"], 0)
        self.assertEqual(second["offset"], 10)
        self.assertEqual(len(out["results"]), 12)
        self.assertEqual(out["results"][-1]["id"], "E-11")
        self.assertEqual(out["total"], 15)

    def test_sploitus_autocomplete_get_query(self) -> None:
        transport = CapturingTransport(SPLOITUS_AUTOCOMPLETE)
        out = sploitus.autocomplete("log4", transport=transport)
        parsed = urlparse(transport.request.url)
        self.assertEqual(transport.request.method, "GET")
        self.assertEqual(parsed.path, "/autocomplete")
        self.assertEqual(parse_qs(parsed.query)["query"], ["log4"])
        self.assertEqual(
            transport.request.headers.get("X-Requested-With"), "sploitus-frontend"
        )
        self.assertEqual([item["text"] for item in out["results"]], SPLOITUS_AUTOCOMPLETE)

    def test_sploitus_exploit_get_html_source_and_cve(self) -> None:
        transport = HtmlTransport(SPLOITUS_EXPLOIT_HTML)
        out = sploitus.exploit(
            "https://sploitus.com/exploit?id=EDB-ID:50592", transport=transport
        )
        parsed = urlparse(transport.request.url)
        self.assertEqual(transport.request.method, "GET")
        self.assertEqual(parsed.path, "/exploit")
        self.assertEqual(parse_qs(parsed.query)["id"], [SPLOITUS_ID])
        hit = out["results"][0]
        self.assertEqual(out["operation"], "exploit")
        self.assertEqual(hit["id"], SPLOITUS_ID)
        self.assertEqual(hit["title"], SPLOITUS_TITLE)
        self.assertEqual(hit["cve"], [SPLOITUS_CVE])
        self.assertIn("print('fixture poc')", hit["source"])
        self.assertEqual(hit["href"], SPLOITUS_HREF)
        self.assertEqual(hit["entry_point"]["parameter"], "methodToCall")
        self.assertEqual(hit["entry_point"]["path"], "ADSearch.cc")
        self.assertEqual(hit["details"]["reporter"], "kozmer")
        self.assertEqual(hit["cvss"]["score"], 10.0)
        self.assertEqual(hit["epss"]["value"], "100.0%")
        self.assertEqual(hit["tags"], ["rce"])
        self.assertEqual(hit["products"][0]["slug"], "apache-log4j2")
        self.assertEqual(hit["related"][0]["id"], "KITPLOIT:RELATED")

    def test_sploitus_cve_and_latest_parse_cards(self) -> None:
        cve_out = sploitus.cve(
            "cve-2021-44228", transport=HtmlTransport(SPLOITUS_CVE_HTML)
        )
        self.assertEqual(cve_out["cve"], SPLOITUS_CVE)
        self.assertEqual(cve_out["nvd"], "https://nvd.nist.gov/vuln/detail/CVE-2021-44228")
        self.assertEqual(cve_out["results"][0]["id"], SPLOITUS_ID)
        self.assertEqual(cve_out["metrics"]["CVSS 3.1"], "10.0 CRITICAL")
        latest_t = HtmlTransport(SPLOITUS_LATEST_HTML)
        latest_out = sploitus.latest(transport=latest_t)
        self.assertEqual(urlparse(latest_t.request.url).path, "/latest")
        hit = latest_out["results"][0]
        self.assertEqual(hit["id"], "9A4610FF-1CD2-5A57-B026-325B42ADF181")
        self.assertEqual(hit["title"], "Fixture latest exploit")
        self.assertEqual(hit["score"], 9.8)
        self.assertEqual(hit["tag"], "GITHUB")

    def test_sploitus_product_follows_rel_next(self) -> None:
        transport = HtmlTransport(SPLOITUS_PRODUCT_HTML, SPLOITUS_PRODUCT_PAGE2_HTML)
        out = sploitus.product("WordPress", limit=2, transport=transport)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(
            urlparse(transport.requests[0].url).path, "/product/wordpress"
        )
        self.assertEqual(
            urlparse(transport.requests[1].url).path, "/product/wordpress/page/2"
        )
        self.assertEqual(out["product"], "wordpress")
        self.assertEqual(out["results"][0]["id"], "CVE-2026-60137")
        self.assertEqual(out["results"][1]["id"], "CVE-2025-6389")
        self.assertEqual(out["total"], 2)

    def test_sploitus_home_widgets(self) -> None:
        transport = HtmlTransport(SPLOITUS_HOME_HTML)
        out = sploitus.home(transport=transport)
        self.assertEqual(urlparse(transport.request.url).path, "/")
        self.assertEqual(out["operation"], "home")
        self.assertEqual(out["widgets"]["trending_cves"][0]["id"], "CVE-2025-55182")
        self.assertEqual(out["widgets"]["trending_cves"][0]["severity"], "CRITICAL 10.0")
        self.assertEqual(out["results"][0]["title"], "Fixture latest exploit")

    def test_exploitdb_search_xhr_header_and_filters(self) -> None:
        transport = CapturingTransport(EDB_SEARCH_PAYLOAD)
        out = exploitdb.search(
            "log4j",
            search_type="remote",
            platform="Java",
            cve="CVE-2021-44228",
            tag="poc",
            verified=True,
            transport=transport,
        )
        req = transport.request
        parsed = urlparse(req.url)
        query = parse_qs(parsed.query)
        self.assertEqual(req.method, "GET")
        self.assertEqual(parsed.hostname, "www.exploit-db.com")
        self.assertEqual(parsed.path, "/search")
        self.assertEqual(req.headers.get("X-Requested-With"), "XMLHttpRequest")
        self.assertEqual(req.headers.get("Referer"), "https://www.exploit-db.com/")
        self.assertEqual(query.get("q"), ["log4j"])
        self.assertEqual(query.get("order[0][column]"), ["0"])
        self.assertEqual(query.get("order[0][dir]"), ["desc"])
        self.assertEqual(query.get("type"), ["remote"])
        self.assertEqual(query.get("platform"), ["java"])
        self.assertEqual(query.get("cve"), ["2021-44228"])
        self.assertEqual(query.get("tag"), ["29"])
        self.assertEqual(query.get("verified"), ["1"])
        hit = out["results"][0]
        self.assertEqual(out["provider"], "exploitdb")
        self.assertEqual(hit["id"], EDB_ID)
        self.assertEqual(hit["title"], EDB_TITLE)
        self.assertEqual(hit["cve"], ["CVE-2021-44228"])
        self.assertEqual(hit["url"], f"https://www.exploit-db.com/exploits/{EDB_ID}")

    def test_exploitdb_latest_and_table_hubs(self) -> None:
        latest_t = CapturingTransport(EDB_LATEST_PAYLOAD)
        latest_out = exploitdb.latest(transport=latest_t)
        latest_q = parse_qs(urlparse(latest_t.request.url).query)
        self.assertEqual(urlparse(latest_t.request.url).path, "/")
        self.assertEqual(latest_q.get("order[0][column]"), ["9"])
        self.assertEqual(latest_out["operation"], "latest")
        self.assertEqual(latest_out["total"], 46664)
        cve_t = CapturingTransport(EDB_SEARCH_PAYLOAD)
        exploitdb.search("CVE-2021-44228", transport=cve_t)
        cve_q = parse_qs(urlparse(cve_t.request.url).query)
        self.assertEqual(cve_q.get("cve"), ["2021-44228"])
        self.assertNotIn("q", cve_q)
        papers_t = CapturingTransport(EDB_PAPERS_PAYLOAD)
        papers_out = exploitdb.papers("polkit", language="English", transport=papers_t)
        pq = parse_qs(urlparse(papers_t.request.url).query)
        self.assertEqual(urlparse(papers_t.request.url).path, "/papers")
        self.assertEqual(pq.get("search[value]"), ["polkit"])
        self.assertEqual(pq.get("lang"), ["english"])
        self.assertEqual(papers_out["results"][0]["title"], EDB_PAPER_TITLE)
        shells_t = CapturingTransport(EDB_SHELLCODES_PAYLOAD)
        shells = exploitdb.shellcodes("calc", platform="windows", transport=shells_t)
        self.assertEqual(urlparse(shells_t.request.url).path, "/shellcodes")
        self.assertEqual(shells["results"][0]["id"], EDB_SHELLCODE_ID)
        ghdb_t = CapturingTransport(EDB_GHDB_PAYLOAD)
        ghdb_out = exploitdb.ghdb("ganglia", category="Files Containing Juicy Info", transport=ghdb_t)
        gq = parse_qs(urlparse(ghdb_t.request.url).query)
        self.assertEqual(urlparse(ghdb_t.request.url).path, "/google-hacking-database")
        self.assertEqual(gq.get("category"), ["8"])
        self.assertEqual(ghdb_out["results"][0]["title"], EDB_DORK_TITLE)

    def test_exploitdb_hubs_raw_authors_stats(self) -> None:
        exploit_out = exploitdb.exploit(
            "EDB-ID:50592", transport=HtmlTransport(EDB_EXPLOIT_HTML)
        )
        self.assertEqual(exploit_out["id"], EDB_ID)
        self.assertEqual(exploit_out["title"], EDB_TITLE)
        self.assertEqual(exploit_out["cve"], ["CVE-2021-44228"])
        self.assertIn("fixture edb poc", exploit_out["source"])
        paper_out = exploitdb.paper(EDB_PAPER_ID, transport=HtmlTransport(EDB_PAPER_HTML))
        self.assertEqual(paper_out["id"], EDB_PAPER_ID)
        self.assertEqual(paper_out["title"], EDB_PAPER_TITLE)
        shell_out = exploitdb.shellcode(
            EDB_SHELLCODE_ID, transport=HtmlTransport(EDB_SHELLCODE_HTML)
        )
        self.assertEqual(shell_out["title"], EDB_SHELLCODE_TITLE)
        dork_out = exploitdb.dork(EDB_DORK_ID, transport=HtmlTransport(EDB_DORK_HTML))
        self.assertEqual(dork_out["id"], EDB_DORK_ID)
        self.assertIn("cluster reports", dork_out["dork"].lower())
        raw_t = CapturingTransport({"unused": True})

        def raw_send(request):
            raw_t.request = request
            return HttpResponse(
                status=200,
                headers={"Content-Type": "text/plain; charset=UTF-8"},
                body=EDB_SOURCE.encode("utf-8"),
            )

        raw_out = exploitdb.raw(EDB_ID, transport=raw_send)
        self.assertEqual(urlparse(raw_t.request.url).path, f"/raw/{EDB_ID}")
        self.assertEqual(raw_out["source"], EDB_SOURCE)
        authors_t = CapturingTransport(EDB_AUTHORS_PAYLOAD)
        authors_out = exploitdb.authors("leon", transport=authors_t)
        self.assertEqual(urlparse(authors_t.request.url).path, "/authors-ajax")
        self.assertEqual(authors_out["results"][0]["name"], EDB_AUTHOR_NAME)
        by_id = exploitdb.authors("8870", transport=CapturingTransport(EDB_AUTHOR_PAYLOAD))
        self.assertEqual(by_id["results"][0]["id"], "8870")
        stats_t = SequentialTransport(
            EDB_LATEST_PAYLOAD, EDB_PAPERS_PAYLOAD, EDB_SHELLCODES_PAYLOAD, EDB_GHDB_PAYLOAD
        )
        stats_out = exploitdb.stats(transport=stats_t)
        self.assertEqual(stats_out["counts"]["exploits"], 46664)
        self.assertEqual(stats_out["counts"]["papers"], 1682)
        self.assertEqual(len(stats_t.requests), 4)

    def test_exploitdb_download_writes_disposition_filename(self) -> None:
        captured = {}

        def send(request):
            captured["request"] = request
            return HttpResponse(
                status=200,
                headers={
                    "Content-Type": "application/txt",
                    "Content-Disposition": 'attachment; filename="50592.py',
                },
                body=EDB_SOURCE.encode("utf-8"),
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = exploitdb.download(EDB_ID, output=tmp, transport=send)
            path = Path(out["path"])
            self.assertEqual(urlparse(captured["request"].url).path, f"/download/{EDB_ID}")
            self.assertEqual(out["filename"], "50592.py")
            self.assertEqual(out["size"], len(EDB_SOURCE.encode("utf-8")))
            self.assertEqual(path.read_text(encoding="utf-8"), EDB_SOURCE)
            self.assertEqual(
                exploitdb.filename_from_headers(
                    {"content-disposition": 'attachment; filename="50592.py'},
                    EDB_ID,
                ),
                "50592.py",
            )

    def test_malpedia_search_two_gets_and_optional_token(self) -> None:
        transport = SequentialTransport(MALPEDIA_FIND_FAMILY, MALPEDIA_FIND_ACTOR)
        out = malpedia.search("emotet", transport=transport)
        self.assertEqual(len(transport.requests), 2)
        family_req, actor_req = transport.requests
        self.assertEqual(family_req.method, "GET")
        self.assertEqual(urlparse(family_req.url).hostname, "malpedia.caad.fkie.fraunhofer.de")
        self.assertEqual(urlparse(family_req.url).path, "/api/find/family/emotet")
        self.assertEqual(urlparse(actor_req.url).path, "/api/find/actor/emotet")
        self.assertNotIn("Authorization", family_req.headers)
        self.assertEqual(out["provider"], "malpedia")
        self.assertEqual(out["families"][0]["name"], MALPEDIA_FAMILY_ID)
        self.assertEqual(out["actors"][0]["name"], MALPEDIA_ACTOR_ID)
        authed = SequentialTransport(MALPEDIA_FIND_FAMILY, MALPEDIA_FIND_ACTOR)
        malpedia.search("emotet", token="fixture-token", transport=authed)
        self.assertEqual(
            authed.requests[0].headers.get("Authorization"), "apitoken fixture-token"
        )

    def test_malpedia_family_yara_lists_version(self) -> None:
        family_t = CapturingTransport(MALPEDIA_FAMILY_PAYLOAD)
        family_out = malpedia.family(MALPEDIA_FAMILY_ID, transport=family_t)
        self.assertEqual(
            urlparse(family_t.request.url).path, f"/api/get/family/{MALPEDIA_FAMILY_ID}"
        )
        self.assertEqual(family_out["common_name"], "Emotet")
        self.assertIn("Geodo", family_out["alt_names"])
        self.assertEqual(family_out["uuid"], MALPEDIA_FAMILY_PAYLOAD["uuid"])
        self.assertIn("471:20200414:understanding:ca95961", family_out["library_entries"])
        actor_t = CapturingTransport(MALPEDIA_ACTOR_PAYLOAD)
        actor_out = malpedia.actor(MALPEDIA_ACTOR_ID, transport=actor_t)
        self.assertEqual(
            urlparse(actor_t.request.url).path, f"/api/get/actor/{MALPEDIA_ACTOR_ID}"
        )
        self.assertEqual(actor_out["common_name"], "APT28")
        yara_t = CapturingTransport(MALPEDIA_YARA_PAYLOAD)
        yara_out = malpedia.yara(MALPEDIA_FAMILY_ID, transport=yara_t)
        self.assertEqual(
            urlparse(yara_t.request.url).path, f"/api/get/yara/{MALPEDIA_FAMILY_ID}"
        )
        self.assertEqual(yara_out["rules"][0]["filename"], MALPEDIA_YARA_NAME)
        self.assertEqual(yara_out["rules"][0]["source"], MALPEDIA_YARA_SOURCE)
        fams = malpedia.families(
            limit=2, transport=CapturingTransport(MALPEDIA_FAMILIES)
        )
        self.assertEqual(fams["results"], MALPEDIA_FAMILIES[:2])
        acts = malpedia.actors(transport=CapturingTransport(MALPEDIA_ACTORS))
        self.assertEqual(acts["results"][0], MALPEDIA_ACTOR_ID)
        ver = malpedia.version(transport=CapturingTransport(MALPEDIA_VERSION_PAYLOAD))
        self.assertEqual(ver["version"], 26109)
        full_fams = malpedia.families(
            full=True, transport=CapturingTransport(MALPEDIA_FAMILIES_FULL)
        )
        self.assertTrue(full_fams["full"])
        self.assertEqual(
            full_fams["results"][MALPEDIA_FAMILY_ID]["common_name"], "Emotet"
        )
        full_acts = malpedia.actors(
            full=True, transport=CapturingTransport(MALPEDIA_ACTORS_FULL)
        )
        self.assertEqual(full_acts["results"][MALPEDIA_ACTOR_ID]["value"], "APT28")

    def test_malpedia_guest_bib_misp_references_yara_index(self) -> None:
        bib_t = HtmlTransport(MALPEDIA_BIB)
        bib_out = malpedia.bib(family="win.owowa", transport=bib_t)
        self.assertEqual(
            urlparse(bib_t.request.url).path, "/api/get/bib/family/win.owowa"
        )
        self.assertEqual(bib_out["entries"][0]["key"], "kupreev:20250410:goffee:adb0ca3")
        self.assertEqual(
            bib_out["entries"][0]["title"],
            "GOFFEE continues to attack organizations in Russia",
        )
        actor_bib = HtmlTransport(MALPEDIA_BIB)
        malpedia.bib(actor="goffee", transport=actor_bib)
        self.assertEqual(
            urlparse(actor_bib.request.url).path, "/api/get/bib/actor/goffee"
        )
        all_bib = HtmlTransport(MALPEDIA_BIB)
        malpedia.bib(transport=all_bib)
        self.assertEqual(urlparse(all_bib.request.url).path, "/api/get/bib")
        misp_out = malpedia.misp(transport=CapturingTransport(MALPEDIA_MISP))
        self.assertEqual(misp_out["galaxy"]["name"], "Malpedia")
        refs_t = CapturingTransport(MALPEDIA_REFERENCES)
        refs = malpedia.references(url=MALPEDIA_REF_URL, transport=refs_t)
        self.assertEqual(urlparse(refs_t.request.url).path, "/api/get/references")
        self.assertEqual(refs["malpedia_version"], 26109)
        self.assertEqual(refs["results"][MALPEDIA_REF_URL][1]["id"], "goffee")
        listed = malpedia.yara_list(
            family=MALPEDIA_FAMILY_ID, transport=CapturingTransport(MALPEDIA_YARA_LIST)
        )
        self.assertEqual(listed["total_rules"], 1)
        self.assertEqual(
            listed["results"][MALPEDIA_FAMILY_ID][0]["path"],
            f"/{MALPEDIA_FAMILY_ID}/yara/tlp_white/{MALPEDIA_YARA_NAME}",
        )
        after_t = CapturingTransport(MALPEDIA_YARA_PAYLOAD)
        after = malpedia.yara_after("2026-01-01", transport=after_t)
        self.assertEqual(
            urlparse(after_t.request.url).path, "/api/get/yara/after/2026-01-01"
        )
        self.assertEqual(after["rules"][0]["filename"], MALPEDIA_YARA_NAME)

    def test_malpedia_yara_dump_and_family_zip_write_files(self) -> None:
        captured = {}

        def send_raw(request):
            captured["request"] = request
            return HttpResponse(
                status=200,
                headers={
                    "Content-Type": "application/yara",
                    "Content-Disposition": "attachment; filename=malpedia_tlp_white.yar",
                },
                body=MALPEDIA_YARA_RAW.encode("utf-8"),
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = malpedia.yara_dump(tlp="white", output=tmp, transport=send_raw)
            path = Path(out["path"])
            self.assertEqual(
                urlparse(captured["request"].url).path, "/api/get/yara/tlp_white/raw"
            )
            self.assertEqual(out["filename"], "malpedia_tlp_white.yar")
            self.assertEqual(path.read_text(encoding="utf-8"), MALPEDIA_YARA_RAW)

        def send_auto(request):
            captured["request"] = request
            return HttpResponse(
                status=200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Disposition": "attachment; filename=malpedia_auto_yar.zip",
                },
                body=MALPEDIA_ZIP,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = malpedia.yara_dump(
                auto=True, as_zip=True, output=tmp, transport=send_auto
            )
            self.assertEqual(
                urlparse(captured["request"].url).path, "/api/get/yara/auto/zip"
            )
            self.assertEqual(Path(out["path"]).read_bytes(), MALPEDIA_ZIP)

        def send_family_zip(request):
            captured["request"] = request
            return HttpResponse(
                status=200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Disposition": 'attachment; filename="win.emotet.zip"',
                },
                body=MALPEDIA_ZIP,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = malpedia.yara(
                MALPEDIA_FAMILY_ID, as_zip=True, output=tmp, transport=send_family_zip
            )
            self.assertEqual(
                urlparse(captured["request"].url).path,
                f"/api/get/yara/{MALPEDIA_FAMILY_ID}/zip",
            )
            self.assertEqual(out["family"], MALPEDIA_FAMILY_ID)
            self.assertEqual(Path(out["path"]).read_bytes(), MALPEDIA_ZIP)

    def test_malpedia_samples_and_download_send_apitoken(self) -> None:
        samples_t = CapturingTransport(MALPEDIA_SAMPLES_PAYLOAD)
        samples_out = malpedia.samples(
            MALPEDIA_FAMILY_ID, token="tok", transport=samples_t
        )
        self.assertEqual(
            urlparse(samples_t.request.url).path,
            f"/api/list/samples/{MALPEDIA_FAMILY_ID}",
        )
        self.assertEqual(samples_t.request.headers.get("Authorization"), "apitoken tok")
        self.assertEqual(samples_out["results"][0]["md5"], MALPEDIA_HASH)
        info_t = CapturingTransport(MALPEDIA_SAMPLE_INFO)
        info = malpedia.sample(MALPEDIA_HASH, token="tok", transport=info_t)
        self.assertEqual(
            urlparse(info_t.request.url).path, f"/api/get/sample/{MALPEDIA_HASH}/info"
        )
        self.assertEqual(info["info"]["family"], MALPEDIA_FAMILY_ID)
        captured = {}

        def send(request):
            captured["request"] = request
            return HttpResponse(
                status=200,
                headers={"Content-Type": "application/zip"},
                body=MALPEDIA_ZIP,
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = malpedia.download(
                MALPEDIA_HASH, token="tok", output=tmp, transport=send
            )
            path = Path(out["path"])
            self.assertEqual(
                urlparse(captured["request"].url).path,
                f"/api/get/sample/{MALPEDIA_HASH}/zip",
            )
            self.assertEqual(captured["request"].headers.get("Authorization"), "apitoken tok")
            self.assertEqual(path.read_bytes(), MALPEDIA_ZIP)
            self.assertEqual(out["filename"], f"{MALPEDIA_HASH}.zip")

    def test_x_transaction_extracts_home_and_is_deterministic(self) -> None:
        self.assertEqual(x_transaction.extract_verification_key(X_HOME_HTML), X_VERIFY_KEY)
        self.assertEqual(x_transaction.extract_ondemand_hash(X_HOME_HTML), X_ONDEMAND_HASH)
        self.assertEqual(x_transaction.extract_indices(X_ONDEMAND_JS), [7, 37, 24, 14])
        self.assertEqual(len(x_transaction.extract_frames(X_HOME_HTML)), 4)
        tx = x_transaction.ClientTransaction.from_documents(X_HOME_HTML, X_ONDEMAND_JS)
        tid_a = tx.generate_transaction_id(
            "GET", "/i/api/graphql/abc/SearchTimeline", time_now=1_700_000_000, random_num=7
        )
        tid_b = tx.generate_transaction_id(
            "GET", "/i/api/graphql/abc/SearchTimeline", time_now=1_700_000_000, random_num=7
        )
        self.assertEqual(tid_a, tid_b)
        self.assertNotIn("=", tid_a)
        raw = base64.b64decode(tid_a + "==")
        self.assertEqual(raw[0], 7)
        with self.assertRaises(ProviderHttpError) as missing:
            x_transaction.extract_verification_key("<html></html>")
        self.assertIn("twitter-site-verification", str(missing.exception))
        with self.assertRaises(ProviderHttpError):
            x_transaction.extract_ondemand_hash("<html></html>")
        with self.assertRaises(ProviderHttpError):
            x_transaction.extract_indices("no indices here")
        with self.assertRaises(ProviderHttpError):
            x_transaction.extract_frames("<svg></svg>")

    def test_x_search_bootstrap_graphql_headers_and_parse(self) -> None:
        transport = ScriptedTransport(
            X_HOME_HTML, X_ONDEMAND_JS, X_MAIN_JS, X_SEARCH_PAYLOAD
        )
        out = x.search(
            "VMProtect LLVM",
            auth_token="auth-fixture",
            ct0="ct0-fixture",
            transport=transport,
        )
        self.assertEqual(len(transport.requests), 4)
        home, ondemand, main, gql = transport.requests
        self.assertEqual(urlparse(home.url).path, "/home")
        self.assertIn("auth_token=auth-fixture", home.headers.get("Cookie", ""))
        self.assertEqual(home.headers.get("x-csrf-token"), "ct0-fixture")
        self.assertIn(f"ondemand.s.{X_ONDEMAND_HASH}a.js", ondemand.url)
        self.assertTrue(urlparse(main.url).path.endswith("/main.fixturea.js"))
        parsed = urlparse(gql.url)
        self.assertEqual(gql.method, "GET")
        self.assertEqual(parsed.path, f"/i/api/graphql/{X_QUERY_SEARCH}/SearchTimeline")
        self.assertTrue(gql.headers.get("Authorization", "").startswith("Bearer "))
        self.assertEqual(gql.headers.get("x-twitter-auth-type"), "OAuth2Session")
        self.assertEqual(gql.headers.get("x-csrf-token"), "ct0-fixture")
        self.assertIn("auth_token=auth-fixture", gql.headers.get("Cookie", ""))
        self.assertTrue(gql.headers.get("x-client-transaction-id"))
        qs = parse_qs(parsed.query)
        variables = json.loads(qs["variables"][0])
        self.assertEqual(variables["rawQuery"], "VMProtect LLVM")
        self.assertEqual(variables["product"], "Latest")
        self.assertEqual(out["provider"], "x")
        self.assertEqual(out["results"][0]["text"], X_TEXT)
        self.assertEqual(out["results"][0]["id"], X_TWEET_ID)
        self.assertEqual(out["results"][0]["user"]["username"], X_USER)
        self.assertIn(X_TWEET_ID, out["results"][0]["url"])
        self.assertEqual(out["cursor"], X_CURSOR)
        features = json.loads(qs["features"][0])
        self.assertEqual(
            set(features),
            {
                "rweb_video_screen_enabled",
                "responsive_web_graphql_timeline_navigation_enabled",
            },
        )
        self.assertFalse(features["rweb_video_screen_enabled"])

    def test_x_search_products_count_cursor_and_fallback_query_id(self) -> None:
        for product, expected in (
            ("latest", "Latest"),
            ("top", "Top"),
            ("people", "People"),
            ("media", "Photos"),
        ):
            transport = ScriptedTransport(
                X_HOME_HTML, X_ONDEMAND_JS, X_MAIN_JS, X_SEARCH_PAYLOAD
            )
            x.search(
                "q",
                auth_token="auth-fixture",
                ct0="ct0-fixture",
                product=product,
                count=7,
                cursor="page-2",
                transport=transport,
            )
            qs = parse_qs(urlparse(transport.requests[-1].url).query)
            variables = json.loads(qs["variables"][0])
            self.assertEqual(variables["product"], expected)
            self.assertEqual(variables["count"], 7)
            self.assertEqual(variables["cursor"], "page-2")
        home = X_HOME_HTML.replace(
            '<script src="https://abs.twimg.com/responsive-web/client-web/main.fixturea.js"></script>',
            "",
        )
        fallback = ScriptedTransport(home, X_ONDEMAND_JS, X_SEARCH_PAYLOAD)
        out = x.search(
            "q", auth_token="auth-fixture", ct0="ct0-fixture", transport=fallback
        )
        self.assertEqual(len(fallback.requests), 3)
        self.assertEqual(
            urlparse(fallback.requests[-1].url).path,
            f"/i/api/graphql/{X_QUERY_SEARCH}/SearchTimeline",
        )
        self.assertEqual(out["results"][0]["id"], X_TWEET_ID)
        with self.assertRaises(ProviderHttpError) as empty:
            x.search("  ", auth_token="a", ct0="b", transport=ScriptedTransport())
        self.assertIn("missing search query", str(empty.exception))
        with self.assertRaises(ProviderHttpError) as product:
            x.search(
                "q",
                auth_token="a",
                ct0="b",
                product="hot",
                transport=ScriptedTransport(
                    X_HOME_HTML, X_ONDEMAND_JS, X_MAIN_JS, X_SEARCH_PAYLOAD
                ),
            )
        self.assertIn("unknown product", str(product.exception))

    def test_x_parse_visibility_note_quoted_replies_and_refs(self) -> None:
        self.assertEqual(x.parse_tweet_ref(X_TWEET_ID), X_TWEET_ID)
        self.assertEqual(
            x.parse_tweet_ref(f"https://x.com/{X_USER}/status/{X_TWEET_ID}"),
            X_TWEET_ID,
        )
        self.assertEqual(
            x.parse_tweet_ref(
                f"https://twitter.com/{X_USER}/status/{X_TWEET_ID}?s=20"
            ),
            X_TWEET_ID,
        )
        self.assertEqual(
            x.parse_tweet_ref(f"https://x.com/i/web/status/{X_TWEET_ID}"),
            X_TWEET_ID,
        )
        with self.assertRaises(ProviderHttpError):
            x.parse_tweet_ref("")
        with self.assertRaises(ProviderHttpError):
            x.parse_tweet_ref("https://x.com/home")
        quoted_id = "99"
        quoted = copy.deepcopy(X_TWEET_RESULT)
        quoted["rest_id"] = quoted_id
        quoted["legacy"]["id_str"] = quoted_id
        quoted["legacy"]["full_text"] = "quoted body"
        wrapped = {
            "__typename": "TweetWithVisibilityResults",
            "tweet": copy.deepcopy(X_TWEET_RESULT),
        }
        wrapped["tweet"]["note_tweet"] = {
            "note_tweet_results": {"result": {"text": "long note body"}}
        }
        wrapped["tweet"]["quoted_status_result"] = {"result": quoted}
        payload = {
            "data": {
                "search_by_raw_query": {
                    "search_timeline": {
                        "timeline": {
                            "instructions": [
                                {
                                    "entries": [
                                        {
                                            "content": {
                                                "itemContent": {
                                                    "tweet_results": {"result": wrapped}
                                                }
                                            }
                                        },
                                        {
                                            "content": {
                                                "cursorType": "ShowMore",
                                                "value": "more-cursor",
                                            }
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        }
        parsed = x.parse_search_response(payload)
        self.assertEqual(parsed["results"][0]["text"], "long note body")
        self.assertEqual(parsed["results"][0]["quoted"]["id"], quoted_id)
        self.assertEqual(parsed["results"][0]["quoted"]["text"], "quoted body")
        self.assertEqual(parsed["cursor"], "more-cursor")
        skipped = x.parse_search_response(
            {
                "data": {
                    "search_by_raw_query": {
                        "search_timeline": {
                            "timeline": {
                                "instructions": [
                                    {
                                        "entries": [
                                            {
                                                "content": {
                                                    "itemContent": {
                                                        "tweet_results": {
                                                            "result": {
                                                                "__typename": "TweetUnavailable"
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        )
        self.assertEqual(skipped["results"], [])
        reply = copy.deepcopy(X_TWEET_RESULT)
        reply["rest_id"] = "reply1"
        reply["legacy"]["id_str"] = "reply1"
        reply["legacy"]["full_text"] = "a reply"
        thread_payload = copy.deepcopy(X_THREAD_PAYLOAD)
        thread_payload["data"]["threaded_conversation_with_injections_v2"][
            "timeline"
        ]["instructions"][0]["entries"].insert(
            1,
            {
                "entryId": "tweet-reply1",
                "content": {"itemContent": {"tweet_results": {"result": reply}}},
            },
        )
        thread = x.parse_thread_response(thread_payload, X_TWEET_ID)
        self.assertEqual(thread["tweet"]["id"], X_TWEET_ID)
        self.assertEqual(thread["tweet"]["type"], "tweet")
        self.assertEqual(len(thread["replies"]), 1)
        self.assertEqual(thread["replies"][0]["text"], "a reply")
        people = x.parse_search_response(
            {
                "data": {
                    "search_by_raw_query": {
                        "search_timeline": {
                            "timeline": {
                                "instructions": [
                                    {
                                        "entries": [
                                            {
                                                "entryId": "user-1",
                                                "content": {
                                                    "itemContent": {
                                                        "itemType": "TimelineUser",
                                                        "user_results": {
                                                            "result": {
                                                                "__typename": "User",
                                                                "rest_id": "13334762",
                                                                "is_blue_verified": True,
                                                                "core": {
                                                                    "name": "GitHub",
                                                                    "screen_name": "github",
                                                                },
                                                                "profile_bio": {
                                                                    "description": "build software"
                                                                },
                                                                "relationship_counts": {
                                                                    "followers": 1
                                                                },
                                                            }
                                                        },
                                                    }
                                                },
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        )
        self.assertEqual(people["results"][0]["type"], "user")
        self.assertEqual(people["results"][0]["username"], "github")
        self.assertEqual(people["results"][0]["url"], "https://x.com/github")
        self.assertEqual(people["results"][0]["bio"], "build software")

    def test_x_thread_tweetdetail_and_url_parse(self) -> None:
        transport = ScriptedTransport(
            X_HOME_HTML, X_ONDEMAND_JS, X_MAIN_JS, X_THREAD_PAYLOAD
        )
        out = x.thread(
            f"https://x.com/{X_USER}/status/{X_TWEET_ID}",
            auth_token="auth-fixture",
            ct0="ct0-fixture",
            cursor="thread-page",
            transport=transport,
        )
        gql = transport.requests[-1]
        parsed = urlparse(gql.url)
        self.assertEqual(parsed.path, f"/i/api/graphql/{X_QUERY_DETAIL}/TweetDetail")
        qs = parse_qs(parsed.query)
        variables = json.loads(qs["variables"][0])
        self.assertEqual(variables["focalTweetId"], X_TWEET_ID)
        self.assertEqual(variables["cursor"], "thread-page")
        toggles = json.loads(qs["fieldToggles"][0])
        self.assertTrue(toggles["withArticleRichContentState"])
        self.assertEqual(out["operation"], "thread")
        self.assertEqual(out["tweet"]["text"], X_TEXT)
        self.assertEqual(out["id"], X_TWEET_ID)
        self.assertEqual(out["cursor"], X_CURSOR)


if __name__ == "__main__":
    unittest.main()
