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

from fixtures import (  # noqa: E402
    BGPT_DOI,
    BGPT_PAYLOAD,
    BGPT_TITLE,
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
    FIRECRAWL_SCRAPE_MD,
    FIRECRAWL_SCRAPE_PAYLOAD,
    FIRECRAWL_SCRAPE_TITLE,
    FIRECRAWL_SCRAPE_URL,
    FIRECRAWL_SEARCH_PAYLOAD,
    FIRECRAWL_SEARCH_SNIPPET,
    FIRECRAWL_SEARCH_TITLE,
    FIRECRAWL_SEARCH_URL,
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


if __name__ == "__main__":
    unittest.main()
