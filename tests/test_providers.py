from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.errors import ProviderHttpError  # noqa: E402
from research_cli.http import HttpResponse  # noqa: E402
from research_cli.providers import bgpt, brave, exa, firecrawl, reddit, sploitus  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
