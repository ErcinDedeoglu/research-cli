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
from research_cli.providers import bgpt, brave, exa, firecrawl  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
