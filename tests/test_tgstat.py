from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from research_cli.errors import MissingKeyError, ProviderHttpError  # noqa: E402
from research_cli.http import HttpResponse  # noqa: E402
from research_cli.keys import require_tgstat_session  # noqa: E402
from research_cli.providers import tgstat  # noqa: E402

from fixtures import (  # noqa: E402
    TGSTAT_CSRF,
    TGSTAT_ERROR_PAYLOAD,
    TGSTAT_LINK,
    TGSTAT_LIST_PAYLOAD,
    TGSTAT_MENTIONS_PAYLOAD,
    TGSTAT_POST_HTML,
    TGSTAT_POST_ID,
    TGSTAT_SEARCH_PAGE,
    TGSTAT_SOURCE_ID,
    TGSTAT_SOURCES_HTML,
    TGSTAT_TEXT,
    TGSTAT_XLSX_BYTES,
    TGSTAT_XLSX_NAME,
    start_fixture_server,
)

COOKIE = tgstat.cookie_header("idr", "sirk")


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
            return HttpResponse(
                status=200,
                headers={"Content-Type": "application/octet-stream"},
                body=bytes(item),
            )
        if isinstance(item, str):
            return HttpResponse(
                status=200,
                headers={"Content-Type": "text/html; charset=UTF-8"},
                body=item.encode("utf-8"),
            )
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(item).encode("utf-8"),
        )


def _search_transport(*payloads: object) -> ScriptedTransport:
    return ScriptedTransport(TGSTAT_SEARCH_PAGE, *payloads)


class KeyTests(unittest.TestCase):
    def test_require_session_cookies(self) -> None:
        with self.assertRaises(MissingKeyError) as ctx:
            require_tgstat_session({})
        self.assertEqual(ctx.exception.provider, "tgstat")
        self.assertEqual(ctx.exception.env_vars, ("TGSTAT_IDR", "TGSTAT_SIRK"))
        with self.assertRaises(MissingKeyError):
            require_tgstat_session({"TGSTAT_IDR": "only-idr"})
        header = require_tgstat_session(
            {
                "TGSTAT_IDR": "abc",
                "TGSTAT_SIRK": "def",
                "TGSTAT_CSRK": "csrf",
                "TGSTAT_SETTINGS": "s",
            }
        )
        self.assertEqual(
            header,
            "tgstat_idrk=abc; tgstat_sirk=def; _tgstat_csrk=csrf; tgstat_settings=s",
        )
        alias = require_tgstat_session({"TGSTAT_IDRK": "from-alias", "TGSTAT_SIRK": "x"})
        self.assertIn("tgstat_idrk=from-alias", alias)


class ParseTests(unittest.TestCase):
    def test_csrf_and_post_html(self) -> None:
        self.assertEqual(tgstat.extract_csrf(TGSTAT_SEARCH_PAGE), TGSTAT_CSRF)
        self.assertEqual(tgstat.extract_csrf("<html></html>"), "")
        parsed = tgstat.parse_posts(TGSTAT_POST_HTML)
        self.assertEqual(len(parsed), 1)
        hit = parsed[0]
        self.assertEqual(hit["id"], TGSTAT_POST_ID)
        self.assertEqual(hit["url"], TGSTAT_LINK)
        self.assertEqual(hit["username"], "fixturechan")
        self.assertEqual(hit["message_id"], 12)
        self.assertEqual(hit["text"], TGSTAT_TEXT)
        self.assertEqual(hit["published"], "31 Aug, 03:49")
        self.assertEqual(hit["title"], "fixturechan")
        self.assertEqual(hit["views"], 42)
        self.assertEqual(hit["quotes"], 3)
        self.assertEqual(hit["shares"], 1)
        self.assertEqual(hit["media"], "photo")
        self.assertTrue(hit["has_media"])
        self.assertEqual(hit["telegram"]["target"], TGSTAT_LINK)
        self.assertTrue(hit["telegram"]["has_media"])
        self.assertFalse(hit["telegram"]["private"])
        self.assertNotIn("deleted", hit)

    def test_joinchat_relative_and_deleted(self) -> None:
        join_html = """
<div id="post-1" class="card post-container deleted ">
  <a href="https://ttttt.me/joinchat/FC59oqTvObIxNGRk/698">Open</a>
  <div class="post-text">private</div>
</div>
"""
        joined = tgstat.parse_post_html(join_html)
        self.assertEqual(joined["invite"], "FC59oqTvObIxNGRk")
        self.assertEqual(
            joined["url"], "https://t.me/joinchat/FC59oqTvObIxNGRk/698"
        )
        self.assertEqual(joined["message_id"], 698)
        self.assertTrue(joined["deleted"])
        self.assertTrue(joined["private"])
        self.assertEqual(
            joined["telegram"]["target"],
            "https://t.me/joinchat/FC59oqTvObIxNGRk/698",
        )
        self.assertFalse(joined["telegram"]["has_media"])
        rel_html = """
<div id="post-2" class="post-container">
  <a href="/en/channel/@fixturechan/12">card</a>
  <div class="post-text">rel</div>
</div>
"""
        rel = tgstat.parse_post_html(rel_html)
        self.assertEqual(rel["url"], "https://t.me/fixturechan/12")
        self.assertEqual(rel["username"], "fixturechan")
        self.assertEqual(rel["message_id"], 12)
        junk_html = """
<div id="post-8" class="post-container">
  <h5><a href="https://tgstat.com/en/channel/@OnlyHack">Only Hack</a></h5>
  <a href="https://t.me/joinchat/6">Open</a>
  <div class="post-text">junk invite</div>
</div>
"""
        junk = tgstat.parse_post_html(junk_html)
        self.assertIsNotNone(junk)
        self.assertNotIn("invite", junk or {})
        target = ((junk or {}).get("telegram") or {}).get("target") or (junk or {}).get("url") or ""
        self.assertNotIn("joinchat/6", str(target))
        self.assertIsNone(tgstat.canonical_telegram_url("https://t.me/joinchat/6"))
        self.assertIsNone(tgstat.canonical_telegram_url("https://t.me/joinchat/abc"))

    def test_dot_dates(self) -> None:
        req = tgstat.build_list_request(
            "q",
            cookie=COOKIE,
            csrf="tok",
            page=0,
            offset=0,
            start="2026-01-02",
            end="1735689600",
        )
        fields = parse_qs(req.body.decode())
        self.assertEqual(fields["startDate"], ["02.01.2026"])
        self.assertEqual(fields["endDate"], ["01.01.2025"])
        with self.assertRaises(ProviderHttpError):
            tgstat.build_list_request(
                "q", cookie=COOKIE, csrf="t", page=0, offset=0, start="not-a-date"
            )


class ClientTests(unittest.TestCase):
    def test_search_csrf_then_list(self) -> None:
        transport = _search_transport(TGSTAT_LIST_PAYLOAD)
        out = tgstat.search("llvm obfuscation", cookie=COOKIE, transport=transport)
        self.assertEqual(len(transport.requests), 2)
        page, listing = transport.requests
        self.assertEqual(page.method, "GET")
        parsed_page = urlparse(page.url)
        self.assertEqual(parsed_page.hostname, "tgstat.com")
        self.assertEqual(parsed_page.path, "/search")
        self.assertIn("tgstat_idrk=idr", page.headers["Cookie"])
        self.assertNotEqual(page.headers.get("X-Requested-With"), "XMLHttpRequest")
        self.assertEqual(listing.method, "POST")
        parsed_list = urlparse(listing.url)
        self.assertEqual(parsed_list.path, "/search/list")
        self.assertEqual(listing.headers["X-Requested-With"], "XMLHttpRequest")
        self.assertIn("application/x-www-form-urlencoded", listing.headers["Content-Type"])
        fields = parse_qs(listing.body.decode(), keep_blank_values=True)
        self.assertEqual(fields["q"], ["llvm obfuscation"])
        self.assertEqual(fields["_tgstat_csrk"], [TGSTAT_CSRF])
        self.assertEqual(fields["peerType"], ["all"])
        self.assertEqual(fields["sort"], ["date"])
        self.assertEqual(fields["page"], ["0"])
        self.assertEqual(fields["offset"], ["0"])
        self.assertEqual(fields["startDate"], [""])
        self.assertEqual(out["provider"], "tgstat")
        self.assertEqual(out["source"], "premium-search")
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["results"][0]["text"], TGSTAT_TEXT)
        self.assertEqual(out["results"][0]["url"], TGSTAT_LINK)
        self.assertEqual(out["cap"], 1000)
        self.assertFalse(out["truncated"])

    def test_search_skips_private_unless_asked(self) -> None:
        html = TGSTAT_POST_HTML + """
<div id="post-2" class="card post-container">
  <a href="https://t.me/joinchat/FC59oqTvObIxNGRk/698">Open</a>
  <div class="post-text">private</div>
</div>
"""
        payload = dict(TGSTAT_LIST_PAYLOAD, html=html, totalCount=2)
        public = tgstat.search("q", cookie=COOKIE, transport=_search_transport(payload))
        self.assertEqual(public["count"], 1)
        self.assertFalse(public["results"][0].get("private"))
        both = tgstat.search(
            "q",
            cookie=COOKIE,
            transport=_search_transport(payload),
            include_private=True,
        )
        self.assertEqual(both["count"], 2)
        self.assertTrue(any(item.get("private") for item in both["results"]))

    def test_me_csrf_probe(self) -> None:
        transport = ScriptedTransport(TGSTAT_SEARCH_PAGE)
        out = tgstat.me(cookie=COOKIE, transport=transport)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["operation"], "me")
        self.assertEqual(transport.requests[0].method, "GET")
        dead = ScriptedTransport("<html></html>")
        with self.assertRaises(ProviderHttpError) as ctx:
            tgstat.me(cookie=COOKIE, transport=dead)
        self.assertIn("recopy", str(ctx.exception).lower())
        self.assertIn("tgstat_idrk", str(ctx.exception).lower())

    def test_search_flags(self) -> None:
        transport = _search_transport(TGSTAT_LIST_PAYLOAD)
        tgstat.search(
            "q",
            cookie=COOKIE,
            limit=5,
            offset=20,
            peer_type="channel",
            start="2026-01-01",
            hide_forwards=True,
            hide_deleted=True,
            strong=True,
            extended=True,
            only_mentioned=True,
            minus_words="spam ads",
            country="us",
            language="en",
            category="tech",
            sort="views",
            transport=transport,
        )
        fields = parse_qs(transport.requests[1].body.decode())
        self.assertEqual(fields["peerType"], ["channel"])
        self.assertEqual(fields["startDate"], ["01.01.2026"])
        self.assertEqual(fields["hideForwards"], ["1"])
        self.assertEqual(fields["hideDeleted"], ["1"])
        self.assertEqual(fields["strongSearch"], ["1"])
        self.assertEqual(fields["extendedSyntax"], ["1"])
        self.assertEqual(fields["onlyMentioned"], ["1"])
        self.assertEqual(fields["minusWords"], ["spam ads"])
        self.assertEqual(fields["country"], ["us"])
        self.assertEqual(fields["language"], ["en"])
        self.assertEqual(fields["category"], ["tech"])
        self.assertEqual(fields["sort"], ["views"])
        self.assertEqual(fields["page"], ["1"])
        self.assertEqual(fields["offset"], ["20"])
        transport = _search_transport(TGSTAT_LIST_PAYLOAD)
        tgstat.search(
            "q",
            cookie=COOKIE,
            views_range="1k-10k",
            channel_id="42",
            source_sort="freq",
            forwards="only",
            transport=transport,
        )
        fields = parse_qs(transport.requests[1].body.decode())
        self.assertEqual(fields["facets[views_range]"], ["1"])
        self.assertEqual(fields["facets[channel_id]"], ["42"])
        self.assertEqual(fields["facets[source_sort]"], ["freq"])
        self.assertEqual(fields["facets[is_forward][1]"], ["1"])
        self.assertEqual(fields["hideForwards"], ["0"])

    def test_search_rejects_empty_and_bad_enums(self) -> None:
        transport = _search_transport(TGSTAT_LIST_PAYLOAD)
        with self.assertRaises(ProviderHttpError):
            tgstat.search("", cookie=COOKIE, transport=transport)
        with self.assertRaises(ProviderHttpError):
            tgstat.search("q", cookie=COOKIE, peer_type="bots", transport=transport)
        with self.assertRaises(ProviderHttpError):
            tgstat.search("q", cookie=COOKIE, sort="score", transport=transport)
        with self.assertRaises(ProviderHttpError):
            tgstat.search("q", cookie=COOKIE, views_range="huge", transport=transport)

    def test_missing_csrf_is_session_error(self) -> None:
        transport = ScriptedTransport("<html><body>login</body></html>")
        with self.assertRaises(ProviderHttpError) as ctx:
            tgstat.search("q", cookie=COOKIE, transport=transport)
        self.assertIn("session", str(ctx.exception).lower())

    def test_status_error_is_provider_error(self) -> None:
        transport = _search_transport(TGSTAT_ERROR_PAYLOAD)
        with self.assertRaises(ProviderHttpError) as ctx:
            tgstat.search("q", cookie=COOKIE, transport=transport)
        self.assertIn("search failed", str(ctx.exception))

    def test_http_500_truncates(self) -> None:
        transport = _search_transport(
            HttpResponse(status=500, headers={}, body=b"boom")
        )
        out = tgstat.search("q", cookie=COOKIE, transport=transport)
        self.assertEqual(out["results"], [])
        self.assertTrue(out["truncated"])

    def test_paginates_until_limit(self) -> None:
        second_html = TGSTAT_POST_HTML.replace(
            str(TGSTAT_POST_ID), "99"
        ).replace("/12", "/13")
        first = {
            **TGSTAT_LIST_PAYLOAD,
            "hasMore": True,
            "nextOffset": 20,
            "nextPage": 1,
            "totalCount": 40,
        }
        second = {
            **TGSTAT_LIST_PAYLOAD,
            "html": second_html,
            "hasMore": False,
            "nextOffset": 40,
            "totalCount": 40,
        }
        transport = _search_transport(first, second)
        out = tgstat.search("q", cookie=COOKIE, limit=40, transport=transport)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["results"][1]["message_id"], 13)

    def test_total_over_cap_marks_truncated(self) -> None:
        payload = {**TGSTAT_LIST_PAYLOAD, "totalCount": 5000, "hasMore": False}
        out = tgstat.search(
            "q", cookie=COOKIE, transport=_search_transport(payload)
        )
        self.assertTrue(out["truncated"])
        self.assertEqual(out["total_count"], 5000)

    def test_mentions_chart(self) -> None:
        transport = _search_transport(TGSTAT_MENTIONS_PAYLOAD)
        out = tgstat.mentions(
            "llvm", cookie=COOKIE, group="month", transport=transport
        )
        self.assertEqual(out["operation"], "mentions")
        self.assertEqual(out["group"], "month")
        self.assertEqual(out["count"][0]["y"], 3)
        self.assertEqual(out["reach"][0]["y"], 100)
        parsed = urlparse(transport.requests[1].url)
        self.assertEqual(parsed.path, "/search/mentions-chart")
        fields = parse_qs(transport.requests[1].body.decode())
        self.assertEqual(fields["group"], ["month"])
        self.assertEqual(fields["q"], ["llvm"])

    def test_export_writes_xlsx(self) -> None:
        transport = ScriptedTransport(
            TGSTAT_SEARCH_PAGE,
            HttpResponse(
                status=200,
                headers={
                    "Content-Type": (
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    "Content-Disposition": f'attachment; filename="{TGSTAT_XLSX_NAME}"',
                },
                body=TGSTAT_XLSX_BYTES,
            ),
        )
        with tempfile.TemporaryDirectory() as raw:
            out = tgstat.export(
                "llvm", cookie=COOKIE, output=raw, transport=transport
            )
            self.assertEqual(out["operation"], "export")
            self.assertEqual(out["filename"], TGSTAT_XLSX_NAME)
            self.assertEqual(Path(out["path"]).read_bytes(), TGSTAT_XLSX_BYTES)
        self.assertEqual(urlparse(transport.requests[1].url).path, "/search/export/xls")

    def test_sources_and_catalogs(self) -> None:
        transport = _search_transport(TGSTAT_SOURCES_HTML)
        out = tgstat.sources("llvm", cookie=COOKIE, transport=transport)
        self.assertEqual(out["operation"], "sources")
        self.assertEqual(out["results"][0]["id"], TGSTAT_SOURCE_ID)
        self.assertEqual(out["results"][0]["freq"], 3)
        self.assertEqual(out["results"][0]["members"], 1000)
        self.assertEqual(out["results"][0]["title"], "Fixture Source")
        self.assertEqual(out["results"][0]["username"], "fixturechan")
        self.assertEqual(urlparse(transport.requests[1].url).path, "/search")
        catalogs = tgstat.catalogs()
        self.assertIn("us", catalogs["countries"])
        self.assertIn("english", catalogs["languages"])
        self.assertIn("tech", catalogs["categories"])
        self.assertEqual(catalogs["views_ranges"], list(tgstat.VIEWS_RANGES))

    def test_download_uses_telegram(self) -> None:
        called: list[tuple[str, str | None]] = []

        def fallback(target: str, output: str | None) -> dict:
            called.append((target, output))
            return {
                "provider": "telegram",
                "operation": "download",
                "path": "/tmp/x.zip",
                "filename": "x.zip",
                "size": 4,
                "id": 12,
            }

        out = tgstat.download(
            "https://ttttt.me/fixturechan/12",
            output="/tmp",
            telegram_download=fallback,
        )
        self.assertEqual(out["source"], "telegram")
        self.assertEqual(called[0][0], "https://t.me/fixturechan/12")
        self.assertEqual(out["path"], "/tmp/x.zip")
        self.assertEqual(out["url"], "https://t.me/fixturechan/12")
        called.clear()
        tgstat.download(
            "https://ttttt.me/joinchat/AbCdefgh/12",
            output="/tmp",
            telegram_download=fallback,
        )
        self.assertEqual(called[0][0], "https://t.me/joinchat/AbCdefgh/12")

    def test_enrich_and_fetch_files(self) -> None:
        webpage = {
            "provider": "telegram",
            "operation": "get",
            "has_media": False,
            "media": {"type": "web_page", "url": "https://e.tld"},
            "message": {"id": 1, "media": {"type": "web_page"}},
        }
        doc = {
            "provider": "telegram",
            "operation": "get",
            "has_media": True,
            "media": {
                "type": "document",
                "name": "a.pdf",
                "mime": "application/pdf",
                "size": 12,
            },
            "message": {"id": 2, "chat": {"username": "pub"}},
        }
        hits = [
            {
                "url": "https://t.me/pub/1",
                "telegram": {
                    "target": "https://t.me/pub/1",
                    "has_media": True,
                    "private": False,
                },
            },
            {
                "url": "https://t.me/pub/2",
                "telegram": {
                    "target": "https://t.me/pub/2",
                    "has_media": True,
                    "private": False,
                },
            },
        ]

        def getter(target: str) -> dict:
            return webpage if target.endswith("/1") else doc

        first = tgstat.enrich_hit(dict(hits[0]), getter)
        self.assertFalse(first["has_media"])
        self.assertEqual(first["telegram"]["media"]["type"], "web_page")
        second = tgstat.enrich_hit(dict(hits[1]), getter)
        self.assertTrue(second["has_media"])
        self.assertEqual(second["telegram"]["mime"], "application/pdf")
        self.assertEqual(second["telegram"]["name"], "a.pdf")
        saved: list[str] = []

        def dl(target: str, output: str | None) -> dict:
            saved.append(target)
            return {
                "path": f"{output}/a.pdf",
                "filename": "a.pdf",
                "size": 12,
                "message": {"chat": {"username": "pub"}},
            }

        work = [dict(hits[0]), dict(hits[1])]
        with tempfile.TemporaryDirectory() as raw:
            tgstat.fetch_files(
                work,
                get_message=getter,
                download_file=dl,
                output=raw,
                media="document",
                jobs=1,
            )
        self.assertEqual(saved, ["https://t.me/pub/2"])
        self.assertEqual(
            work[1]["telegram"]["download"]["filename"], "a.pdf"
        )
        huge = {
            "telegram": {
                "target": "https://t.me/pub/3",
                "has_media": True,
                "private": False,
                "media": {"type": "document", "size": 99_000_000},
                "size": 99_000_000,
            }
        }
        tgstat.fetch_files(
            [huge],
            download_file=dl,
            output="/tmp",
            jobs=1,
        )
        self.assertEqual(huge["telegram"]["skipped"], "too large")
        private = {
            "telegram": {
                "target": "https://t.me/joinchat/AbCdefgh/1",
                "has_media": True,
                "private": True,
                "media": {"type": "document"},
            }
        }
        saved.clear()
        tgstat.fetch_files(
            [dict(private)],
            download_file=dl,
            output="/tmp",
            jobs=1,
        )
        self.assertEqual(saved, [])
        tgstat.fetch_files(
            [dict(private)],
            download_file=dl,
            output="/tmp",
            include_private=True,
            jobs=1,
        )
        self.assertEqual(saved, ["https://t.me/joinchat/AbCdefgh/1"])
        with self.assertRaises(ProviderHttpError):
            tgstat.fetch_files([], media="audio")

    def test_download_without_telegram(self) -> None:
        with self.assertRaises(ProviderHttpError) as ctx:
            tgstat.download("https://t.me/fixturechan/12")
        self.assertIn("no file bytes", str(ctx.exception).lower())
        with self.assertRaises(ProviderHttpError):
            tgstat.download("")

    def test_fixture_server_search(self) -> None:
        server, base = start_fixture_server()
        try:
            out = tgstat.search("llvm", cookie=COOKIE, origin=base)
            self.assertEqual(out["results"][0]["text"], TGSTAT_TEXT)
            self.assertEqual(out["results"][0]["url"], TGSTAT_LINK)
            mentions = tgstat.mentions("llvm", cookie=COOKIE, origin=base)
            self.assertEqual(mentions["count"][0]["y"], 3)
            sources = tgstat.sources("llvm", cookie=COOKIE, origin=base)
            self.assertEqual(sources["results"][0]["id"], TGSTAT_SOURCE_ID)
            with tempfile.TemporaryDirectory() as raw:
                exported = tgstat.export(
                    "llvm", cookie=COOKIE, origin=base, output=raw
                )
                self.assertEqual(Path(exported["path"]).read_bytes(), TGSTAT_XLSX_BYTES)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
