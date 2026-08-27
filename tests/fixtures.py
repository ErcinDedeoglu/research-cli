from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BGPT_TITLE = "Fixture BGPT Paper on CRISPR"
BGPT_DOI = "10.1234/bgpt.fixture"
BGPT_PAYLOAD = {
    "results": [
        {
            "title": BGPT_TITLE,
            "doi": BGPT_DOI,
            "central_claim": "Fixture claim about CRISPR delivery.",
        }
    ]
}

BRAVE_TITLE = "Fixture Brave Search Hit"
BRAVE_URL = "https://brave.example/hit"
BRAVE_PAYLOAD = {
    "type": "search",
    "web": {
        "results": [
            {
                "title": BRAVE_TITLE,
                "url": BRAVE_URL,
                "description": "Fixture brave snippet",
            }
        ]
    },
}

EXA_SEARCH_TITLE = "Fixture Exa Search Hit"
EXA_SEARCH_URL = "https://exa.example/hit"
EXA_SEARCH_PAYLOAD = {
    "results": [
        {
            "title": EXA_SEARCH_TITLE,
            "url": EXA_SEARCH_URL,
            "id": EXA_SEARCH_URL,
        }
    ]
}

EXA_CONTENTS_TITLE = "Fixture Exa Contents Page"
EXA_CONTENTS_URL = "https://exa.example/page"
EXA_CONTENTS_TEXT = "Fixture page text from Exa contents."
EXA_CONTENTS_PAYLOAD = {
    "results": [
        {
            "title": EXA_CONTENTS_TITLE,
            "url": EXA_CONTENTS_URL,
            "text": EXA_CONTENTS_TEXT,
            "highlights": ["Fixture highlight"],
        }
    ]
}

FIRECRAWL_SCRAPE_TITLE = "Fixture Firecrawl Page"
FIRECRAWL_SCRAPE_URL = "https://firecrawl.example/page"
FIRECRAWL_SCRAPE_MD = "# Fixture Firecrawl Markdown"
FIRECRAWL_SCRAPE_PAYLOAD = {
    "success": True,
    "data": {
        "markdown": FIRECRAWL_SCRAPE_MD,
        "metadata": {
            "title": FIRECRAWL_SCRAPE_TITLE,
            "sourceURL": FIRECRAWL_SCRAPE_URL,
            "url": FIRECRAWL_SCRAPE_URL,
        },
    },
}

FIRECRAWL_SEARCH_TITLE = "Fixture Firecrawl Search Hit"
FIRECRAWL_SEARCH_URL = "https://firecrawl.example/hit"
FIRECRAWL_SEARCH_SNIPPET = "Fixture firecrawl snippet"
FIRECRAWL_SEARCH_PAYLOAD = {
    "success": True,
    "data": {
        "web": [
            {
                "url": FIRECRAWL_SEARCH_URL,
                "title": FIRECRAWL_SEARCH_TITLE,
                "description": FIRECRAWL_SEARCH_SNIPPET,
            }
        ]
    },
}

BRAVE_LLM_TITLE = "Fixture Brave LLM Context Page"
BRAVE_LLM_URL = "https://brave.example/context"
BRAVE_LLM_TEXT = "Fixture llm context snippet about RAG."
BRAVE_LLM_PAYLOAD = {
    "grounding": {
        "generic": [
            {
                "url": BRAVE_LLM_URL,
                "title": BRAVE_LLM_TITLE,
                "snippets": [BRAVE_LLM_TEXT],
            }
        ],
        "map": [],
    },
    "sources": {
        BRAVE_LLM_URL: {"title": BRAVE_LLM_TITLE, "hostname": "brave.example"}
    },
}

FIRECRAWL_MAP_URL = "https://docs.firecrawl.dev/webhooks"
FIRECRAWL_MAP_TITLE = "Fixture Firecrawl Map Link"
FIRECRAWL_MAP_PAYLOAD = {
    "success": True,
    "links": [
        {
            "url": FIRECRAWL_MAP_URL,
            "title": FIRECRAWL_MAP_TITLE,
            "description": "Fixture map description",
        }
    ],
}

PAPER_ID = "arxiv:2105.05233"
PAPER_TITLE = "Fixture Firecrawl Paper Diffusion"
PAPER_ABSTRACT = "Fixture abstract from the research index."
PAPER_PASSAGE = "Fixture passage answering the architecture question."
PAPERS_SEARCH_PAYLOAD = {
    "success": True,
    "results": [
        {
            "paperId": "2014215642691656232",
            "primaryId": PAPER_ID,
            "title": PAPER_TITLE,
            "abstract": PAPER_ABSTRACT,
            "score": 0.9,
        }
    ],
}
PAPERS_INSPECT_PAYLOAD = {
    "success": True,
    "paper": {
        "paperId": "2014215642691656232",
        "primaryId": PAPER_ID,
        "title": PAPER_TITLE,
        "abstract": PAPER_ABSTRACT,
        "authors": "Fixture Author",
        "categories": ["cs.LG"],
    },
}
PAPERS_READ_PAYLOAD = {
    "success": True,
    "passages": [{"text": PAPER_PASSAGE, "score": 0.8}],
}
PAPERS_RELATED_TITLE = "Fixture Related Diffusion Paper"
PAPERS_RELATED_PAYLOAD = {
    "success": True,
    "results": [
        {
            "paperId": "482107036680302043",
            "primaryId": "arxiv:2006.11239",
            "title": PAPERS_RELATED_TITLE,
            "abstract": "Fixture related abstract",
            "score": 0.03,
        }
    ],
    "poolSize": 40,
    "truncated": False,
}

_POST_ROUTES = {
    "/api/mcp-search": BGPT_PAYLOAD,
    "/search": EXA_SEARCH_PAYLOAD,
    "/contents": EXA_CONTENTS_PAYLOAD,
    "/v2/scrape": FIRECRAWL_SCRAPE_PAYLOAD,
    "/v2/search": FIRECRAWL_SEARCH_PAYLOAD,
    "/v2/map": FIRECRAWL_MAP_PAYLOAD,
}


class FixtureHandler(BaseHTTPRequestHandler):
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            return self.rfile.read(length)
        return b""

    def _send(self, status: int, payload: object) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/res/v1/web/search":
            self._send(200, BRAVE_PAYLOAD)
            return
        if path == "/res/v1/llm/context":
            self._send(200, BRAVE_LLM_PAYLOAD)
            return
        if path == "/v2/search/research/papers":
            self._send(200, PAPERS_SEARCH_PAYLOAD)
            return
        if path.endswith("/similar"):
            self._send(200, PAPERS_RELATED_PAYLOAD)
            return
        if path.startswith("/v2/search/research/papers/"):
            if "query=" in parsed.query:
                self._send(200, PAPERS_READ_PAYLOAD)
                return
            self._send(200, PAPERS_INSPECT_PAYLOAD)
            return
        self._send(404, {"error": f"no fixture for GET {path}"})

    def do_POST(self) -> None:  # noqa: N802
        self._read_body()
        path = urlparse(self.path).path
        payload = _POST_ROUTES.get(path)
        if payload is None:
            self._send(404, {"error": f"no fixture for POST {path}"})
            return
        self._send(200, payload)


def start_fixture_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"
