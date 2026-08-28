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

REDDIT_TITLE = "Fixture Reddit Post"
REDDIT_PERMALINK = "/r/python/comments/abc123/fixture_post/"
REDDIT_URL = "https://www.reddit.com/r/python/comments/abc123/fixture_post/"
REDDIT_LINK_URL = "https://example.com/article"
REDDIT_SELFTEXT = "Fixture reddit selftext"
REDDIT_TOKEN = "fixture-reddit-token"
REDDIT_TOKEN_PAYLOAD = {
    "access_token": REDDIT_TOKEN,
    "token_type": "bearer",
    "expires_in": 3600,
    "scope": "*",
}
REDDIT_POST_ID = "abc123"
REDDIT_SEARCH_PAYLOAD = {
    "kind": "Listing",
    "data": {
        "children": [
            {
                "kind": "t3",
                "data": {
                    "id": REDDIT_POST_ID,
                    "title": REDDIT_TITLE,
                    "permalink": REDDIT_PERMALINK,
                    "url": REDDIT_LINK_URL,
                    "subreddit": "python",
                    "author": "fixture_user",
                    "score": 42,
                    "num_comments": 7,
                    "selftext": REDDIT_SELFTEXT,
                    "created_utc": 1700000000.0,
                },
            }
        ]
    },
}

SPLOITUS_TITLE = "Fixture Sploitus Log4j RCE"
SPLOITUS_ID = "EDB-ID:50592"
SPLOITUS_HREF = "https://gitlab.example/exploits/50592.py"
SPLOITUS_SOURCE = "## https://sploitus.com/exploit?id=EDB-ID:50592\nprint('fixture poc')"
SPLOITUS_CVE = "CVE-2021-44228"
SPLOITUS_SEARCH_PAYLOAD = {
    "exploits": [
        {
            "title": SPLOITUS_TITLE,
            "score": 10.0,
            "href": SPLOITUS_HREF,
            "type": "exploitdb",
            "published": "2021-12-14",
            "id": SPLOITUS_ID,
            "source": SPLOITUS_SOURCE,
            "language": "python",
            "cve_list": [SPLOITUS_CVE],
            "cve_string": SPLOITUS_CVE,
            "view_count": 12,
            "description": "Fixture sploitus description",
            "epss_score": 0.99,
        }
    ],
    "exploits_total": 42,
}

SPLOITUS_TOOL_TITLE = "Fixture Sploitus C2 Tool"
SPLOITUS_TOOL_ID = "KITPLOIT:TOOLS-FIXTURE-C2"
SPLOITUS_TOOL_PAYLOAD = {
    "exploits": [
        {
            "title": SPLOITUS_TOOL_TITLE,
            "href": "https://kitploit.example/c2",
            "type": "kitploit",
            "id": SPLOITUS_TOOL_ID,
            "download": "https://kitploit.example/c2.zip",
            "published": "2026-08-27",
            "view_count": 2,
            "description": "Fixture hacktool description",
        }
    ],
    "exploits_total": 7,
}

SPLOITUS_AUTOCOMPLETE = ["log4j", "log4j2", "log4shell"]
SPLOITUS_EXPLOIT_HTML = """<!doctype html><html><body data-page=exploit>
<script type=application/ld+json>{"@graph":[{"@type":"TechArticle","headline":"Fixture Sploitus Log4j RCE","url":"https://sploitus.com/exploit?id=EDB-ID:50592","description":"Fixture exploit description","datePublished":"2021-12-14T00:00:00","interactionStatistic":{"@type":"InteractionCounter","userInteractionCount":12},"about":[{"@type":"Thing","identifier":"CVE-2021-44228"}],"hasPart":{"@type":"SoftwareSourceCode","programmingLanguage":"Python","codeRepository":"https://gitlab.example/exploits/50592.py"}}]}</script>
<div class="avatar logo logo_exploitdb"></div>
<pre><code data-lang=python>## https://sploitus.com/exploit?id=EDB-ID:50592
print('fixture poc')</code></pre>
</body></html>"""
SPLOITUS_CVE_HTML = """<!doctype html><html><body data-page=cve>
<script type=application/ld+json>{"@graph":[{"@type":"CollectionPage","name":"1 known exploits for CVE-2021-44228","about":{"@type":"Thing","identifier":"CVE-2021-44228","url":"https://nvd.nist.gov/vuln/detail/CVE-2021-44228","description":"Fixture CVE description"},"mainEntity":{"@type":"ItemList","numberOfItems":1}}]}</script>
<p class="vulnerability__description vulnerability__description--full">Fixture CVE description</p>
<dt class=card__metric-label>CVSS 3.1</dt><dd class=card__metric-value>10.0 CRITICAL</dd>
<a href="/exploit?id=EDB-ID:50592" class=vulnerability><div class=vulnerability__content><div class=vulnerability__title>Fixture Sploitus Log4j RCE</div><div class=vulnerability__meta><span class=vulnerability__meta-item>2021-12-14</span><span class=vulnerability__tag>EXPLOITDB</span></div></div></a>
</body></html>"""
SPLOITUS_PRODUCT_HTML = """<!doctype html><html><body data-page=product>
<link href=/product/wordpress/page/2 rel=next>
<script type=application/ld+json>{"@graph":[{"@type":"CollectionPage","name":"2 exploited vulnerabilities in Wordpress","about":{"@type":"SoftwareApplication","name":"Wordpress"},"mainEntity":{"@type":"ItemList","numberOfItems":2}}]}</script>
<dt class=card__metric-label>With known exploits</dt><dd class=card__metric-value>2</dd>
<a class=vulnerability href=/cve/CVE-2026-60137><div class=vulnerability__content><div class=vulnerability__title>CVE-2026-60137 <span class=vulnerability__count>3 exploits</span></div><div class=vulnerability__meta><span class=vulnerability__meta-item>CVSS 9.1 CRITICAL</span><span class=vulnerability__tag>FIX AVAILABLE</span></div></div></a>
</body></html>"""
SPLOITUS_PRODUCT_PAGE2_HTML = """<!doctype html><html><body data-page=product>
<script type=application/ld+json>{"@graph":[{"@type":"CollectionPage","name":"2 exploited vulnerabilities in Wordpress","mainEntity":{"@type":"ItemList","numberOfItems":2}}]}</script>
<a class=vulnerability href=/cve/CVE-2025-6389><div class=vulnerability__content><div class=vulnerability__title>CVE-2025-6389</div></div></a>
</body></html>"""
SPLOITUS_LATEST_HTML = """<!doctype html><html><body data-page=hub>
<nav class=pagination><span class=pagination__status>Page 1</span></nav>
<a href="/exploit?id=9A4610FF-1CD2-5A57-B026-325B42ADF181" class=vulnerability><div class=vulnerability__content><div class=vulnerability__title>Fixture latest exploit</div><div class=vulnerability__meta><span class=vulnerability__meta-item>2026-08-28</span><span class=vulnerability__meta-item>9.8</span><span class=vulnerability__tag>GITHUB</span></div></div></a>
</body></html>"""

REDDIT_COMMENT_BODY = "Fixture reddit comment about CRISPR."
REDDIT_REPLY_BODY = "Fixture nested reply"
REDDIT_THREAD_PAYLOAD = [
    REDDIT_SEARCH_PAYLOAD,
    {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "cmt456",
                        "author": "commenter",
                        "body": REDDIT_COMMENT_BODY,
                        "score": 11,
                        "created_utc": 1700000100.0,
                        "permalink": "/r/python/comments/abc123/fixture_post/cmt456/",
                        "replies": {
                            "kind": "Listing",
                            "data": {
                                "children": [
                                    {
                                        "kind": "t1",
                                        "data": {
                                            "id": "cmt789",
                                            "author": "replier",
                                            "body": REDDIT_REPLY_BODY,
                                            "score": 3,
                                            "created_utc": 1700000200.0,
                                            "permalink": "/r/python/comments/abc123/fixture_post/cmt789/",
                                            "replies": "",
                                        },
                                    }
                                ]
                            },
                        },
                    },
                }
            ]
        },
    },
]

_POST_ROUTES = {
    "/api/mcp-search": BGPT_PAYLOAD,
    "/search": EXA_SEARCH_PAYLOAD,
    "/contents": EXA_CONTENTS_PAYLOAD,
    "/v2/scrape": FIRECRAWL_SCRAPE_PAYLOAD,
    "/v2/search": FIRECRAWL_SEARCH_PAYLOAD,
    "/v2/map": FIRECRAWL_MAP_PAYLOAD,
    "/api/v1/access_token": REDDIT_TOKEN_PAYLOAD,
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

    def _send_html(self, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
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
        if path == "/autocomplete":
            self._send(200, SPLOITUS_AUTOCOMPLETE)
            return
        if path == "/exploit":
            self._send_html(SPLOITUS_EXPLOIT_HTML)
            return
        if path.startswith("/cve/"):
            self._send_html(SPLOITUS_CVE_HTML)
            return
        if path == "/product/wordpress/page/2":
            self._send_html(SPLOITUS_PRODUCT_PAGE2_HTML)
            return
        if path.startswith("/product/"):
            self._send_html(SPLOITUS_PRODUCT_HTML)
            return
        if path.startswith("/latest"):
            self._send_html(SPLOITUS_LATEST_HTML)
            return
        if path == "/search" or path.endswith("/search"):
            self._send(200, REDDIT_SEARCH_PAYLOAD)
            return
        if "/comments/" in path:
            self._send(200, REDDIT_THREAD_PAYLOAD)
            return
        if path.startswith("/r/") and path.rsplit("/", 1)[-1] in {
            "hot",
            "new",
            "top",
            "rising",
            "controversial",
        }:
            self._send(200, REDDIT_SEARCH_PAYLOAD)
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
        if (
            path == "/search"
            and self.headers.get("X-Requested-With") == "sploitus-frontend"
        ):
            self._send(200, SPLOITUS_SEARCH_PAYLOAD)
            return
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
