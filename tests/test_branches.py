from __future__ import annotations

import argparse
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.cli import (  # noqa: E402
    _csv,
    _dispatch,
    _dispatch_exploitdb,
    _dispatch_firecrawl,
    _dispatch_malpedia,
    _dispatch_reddit,
    _dispatch_sploitus,
    _dispatch_x,
    _schedule_update,
    help_topic_payload,
    main,
)
from research_cli.errors import MissingKeyError, ProviderHttpError, UpdateError  # noqa: E402
from research_cli.http import (  # noqa: E402
    HttpRequest,
    HttpResponse,
    encode_query,
    execute_json,
    join_url,
    ssl_context,
    urllib_transport,
    with_query,
)
from research_cli.keys import (  # noqa: E402
    default_env_path,
    optional_bgpt_key,
    parse_env_file,
    require_brave_key,
    require_exa_key,
    require_firecrawl_key,
    require_reddit_credentials,
    require_telegram_app,
    require_telegram_session,
    require_tgstat_session,
    require_x_credentials,
)
from research_cli.providers import (  # noqa: E402
    bgpt,
    brave,
    exa,
    exploitdb,
    firecrawl,
    malpedia,
    reddit,
    sploitus,
    x,
    x_transaction,
)
from research_cli.providers import firecrawl_papers as papers  # noqa: E402
from research_cli.update import (  # noqa: E402
    Install,
    _allowed_download_url,
    _arch,
    acquire_update_lock,
    asset_name,
    cache_dir,
    choose_asset,
    cleanup_old_binary,
    current_install,
    detect_kind,
    download_asset,
    fetch_latest_release,
    parse_version,
    pid_is_running,
    replace_executable,
    run_self_update,
    spawn_background_update,
    wait_for_parent,
)


class ErrorsHttpKeysTests(unittest.TestCase):
    def test_provider_http_error_truncates_long_body(self) -> None:
        exc = ProviderHttpError("x", 500, "z" * 2500)
        self.assertIn("…", str(exc))
        self.assertLess(len(str(exc)), 2600)
        empty = ProviderHttpError("x", 404, "  ")
        self.assertIn("empty body", str(empty))

    def test_join_url_query_and_json_errors(self) -> None:
        self.assertEqual(join_url("http://h", "p"), "http://h/p")
        self.assertEqual(encode_query({"a": True, "b": False, "c": None}), "a=true&b=false")
        self.assertEqual(encode_query({"q": ["x", None, ""]}), "q=x")
        self.assertEqual(with_query("http://h/p", {}), "http://h/p")
        self.assertIn("&b=1", with_query("http://h/p?a=1", {"b": 1}))
        with self.assertRaises(ProviderHttpError):
            execute_json(
                HttpRequest("GET", "http://x"),
                provider="p",
                transport=lambda _r: (_ for _ in ()).throw(TimeoutError("t")),
            )
        with self.assertRaises(ProviderHttpError) as empty:
            execute_json(
                HttpRequest("GET", "http://x"),
                provider="p",
                transport=lambda _r: HttpResponse(200, {}, b"  "),
            )
        self.assertIn("empty", str(empty.exception))
        with self.assertRaises(ProviderHttpError) as bad:
            execute_json(
                HttpRequest("GET", "http://x"),
                provider="p",
                transport=lambda _r: HttpResponse(200, {}, b"not-json"),
            )
        self.assertIn("invalid JSON", str(bad.exception))

    def test_urllib_httperror_and_ssl_frozen(self) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_error(418, "nope")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            response = urllib_transport(
                HttpRequest("GET", f"http://{host}:{port}/missing"), timeout=5
            )
            self.assertEqual(response.status, 418)
        finally:
            server.shutdown()
            server.server_close()
        with patch.dict(os.environ, {"SSL_CERT_FILE": "", "SSL_CERT_DIR": ""}, clear=False):
            os.environ.pop("SSL_CERT_FILE", None)
            os.environ.pop("SSL_CERT_DIR", None)
            with patch.dict(sys.modules, {"certifi": None}):
                real_import = __import__

                def boom(name, *args, **kwargs):
                    if name == "certifi":
                        raise ImportError("no certifi")
                    return real_import(name, *args, **kwargs)

                with patch("builtins.__import__", boom):
                    with patch.object(sys, "frozen", True, create=True):
                        with patch("research_cli.http.Path.is_file", return_value=True):
                            with patch(
                                "research_cli.http.ssl.create_default_context"
                            ) as created:
                                created.return_value = ssl.SSLContext(
                                    ssl.PROTOCOL_TLS_CLIENT
                                )
                                ctx = ssl_context()
                                created.assert_called()
                                self.assertIs(ctx, created.return_value)

    def test_keys_windows_parse_and_require(self) -> None:
        from pathlib import PurePosixPath

        with patch("research_cli.keys.os.name", "nt"), patch(
            "research_cli.keys.Path", PurePosixPath
        ):
            path = default_env_path({"APPDATA": "/tmp/appdata"})
            self.assertIn("research-cli", str(path))
        self.assertIsNone(optional_bgpt_key({}))
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            path.write_text("not-a-key\nKEY=value\n", encoding="utf-8")
            parsed = parse_env_file(path)
            self.assertEqual(parsed["KEY"], "value")
            self.assertNotIn("not-a-key", parsed)
        with self.assertRaises(MissingKeyError):
            require_brave_key({})
        with self.assertRaises(MissingKeyError):
            require_exa_key({})
        with self.assertRaises(MissingKeyError):
            require_firecrawl_key({})
        with self.assertRaises(MissingKeyError):
            require_reddit_credentials({"REDDIT_CLIENT_ID": "x"})
        with self.assertRaises(MissingKeyError):
            require_x_credentials({"X_AUTH_TOKEN": "t"})
        with self.assertRaises(MissingKeyError):
            require_telegram_app({"TELEGRAM_API_ID": "1"})
        with self.assertRaises(MissingKeyError):
            require_telegram_session({"RESEARCH_CLI_NO_ENV_FILE": "1"})
        with self.assertRaises(MissingKeyError):
            require_tgstat_session({"TGSTAT_IDR": "i"})


class UpdateBranchTests(unittest.TestCase):
    def test_detect_kind_asset_cache_and_errors(self) -> None:
        self.assertEqual(parse_version(""), (0,))
        self.assertEqual(parse_version("1a.2"), (1, 2))
        self.assertEqual(detect_kind(frozen=True), "frozen")
        self.assertEqual(detect_kind(frozen=False, argv0="app.pyz"), "zipapp")
        frozen = current_install(kind="frozen", system="Darwin", machine="arm64")
        self.assertEqual(frozen.kind, "frozen")
        zipapp = current_install(
            kind="zipapp", argv0="/tmp/research-cli.pyz", system="Linux", machine="x86_64"
        )
        self.assertTrue(str(zipapp.path).endswith("research-cli.pyz"))
        self.assertEqual(asset_name("frozen", "Windows", "amd64"), "research-cli-Windows-x86_64.exe")
        self.assertEqual(asset_name("frozen", "Linux", "aarch64"), "research-cli-Linux-aarch64")
        with self.assertRaises(UpdateError):
            asset_name("frozen", "FreeBSD", "x86_64")
        with self.assertRaises(UpdateError):
            _arch("Linux", "riscv")
        self.assertEqual(
            cache_dir({"XDG_CACHE_HOME": "/tmp/xdg"}), Path("/tmp/xdg") / "research-cli"
        )
        from pathlib import PurePosixPath

        with patch("research_cli.update.os.name", "nt"), patch(
            "research_cli.update.Path", PurePosixPath
        ):
            self.assertEqual(
                cache_dir({"LOCALAPPDATA": "/tmp/loc"}),
                PurePosixPath("/tmp/loc") / "research-cli",
            )
        self.assertFalse(_allowed_download_url("https://evil.example/bin"))
        self.assertTrue(_allowed_download_url("https://github.com/x/y"))
        with self.assertRaises(UpdateError):
            download_asset("https://evil.example/x", transport=None, timeout=1)
        with self.assertRaises(UpdateError):
            fetch_latest_release(
                environ={},
                transport=lambda _r: HttpResponse(500, {}, b"err"),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            fetch_latest_release(
                environ={},
                transport=lambda _r: HttpResponse(200, {}, b"not-json"),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            fetch_latest_release(
                environ={},
                transport=lambda _r: HttpResponse(200, {}, b"[1]"),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            fetch_latest_release(
                environ={},
                transport=lambda _r: (_ for _ in ()).throw(TimeoutError("t")),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            choose_asset({"assets": "nope"}, "x")
        with self.assertRaises(UpdateError):
            choose_asset({"assets": [{"name": "x"}]}, "x")
        with self.assertRaises(UpdateError):
            download_asset(
                "https://github.com/x",
                transport=lambda _r: HttpResponse(404, {}, b"missing"),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            download_asset(
                "https://github.com/x",
                transport=lambda _r: HttpResponse(200, {}, b""),
                timeout=1,
            )
        with self.assertRaises(UpdateError):
            download_asset(
                "https://github.com/x",
                transport=lambda _r: HttpResponse(200, {}, b"<html>"),
                timeout=1,
            )
        big = b"a" * (200 * 1024 * 1024 + 1)
        with self.assertRaises(UpdateError):
            download_asset(
                "https://github.com/x",
                transport=lambda _r: HttpResponse(200, {}, big),
                timeout=1,
            )

    def test_replace_lock_pid_and_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "bin"
            target.write_bytes(b"old")
            replace_executable(target, b"new", windows=True)
            self.assertEqual(target.read_bytes(), b"new")
            with patch("research_cli.update.os.chmod", side_effect=OSError("chmod")):
                replace_executable(target, b"newer", windows=False)
            cleanup_old_binary(None)
            with patch("pathlib.Path.unlink", side_effect=OSError("busy")):
                cleanup_old_binary(target)
            windows_target = Path(raw) / "win.bin"
            windows_target.write_bytes(b"a")
            with patch("research_cli.update.os.replace", side_effect=OSError("inuse")):
                with self.assertRaises(OSError):
                    replace_executable(windows_target, b"b", windows=True)
        self.assertFalse(pid_is_running(0))
        with patch("os.kill", side_effect=ProcessLookupError):
            self.assertFalse(pid_is_running(99))
        with patch("os.kill", side_effect=PermissionError):
            self.assertTrue(pid_is_running(99))
        with patch("os.kill", side_effect=OSError("e")):
            self.assertFalse(pid_is_running(99))
        wait_for_parent({})
        wait_for_parent({"RESEARCH_CLI_UPDATE_WAIT_PID": "abc"})
        with tempfile.TemporaryDirectory() as raw:
            env = {"RESEARCH_CLI_CACHE_DIR": raw}
            with patch("pathlib.Path.open", side_effect=OSError("lock")):
                self.assertIsNone(acquire_update_lock(env, blocking=False))
            frozen_path = Path(raw) / "bin"
            frozen_path.write_bytes(b"x")
            self.assertTrue(
                spawn_background_update(
                    environ=env,
                    install=Install("frozen", frozen_path, "Darwin", "arm64"),
                    popen=lambda *a, **k: MagicMock(),
                )
            )


class ProviderParseBranchTests(unittest.TestCase):
    def test_bgpt_brave_exa_firecrawl_edges(self) -> None:
        req = bgpt.build_search_request("q", days_back=3, api_key="k")
        self.assertIn(b"days_back", req.body or b"")
        self.assertEqual(bgpt.parse_search_response(["nope", {"id": "1"}])["results"][0]["id"], "1")
        self.assertEqual(bgpt.parse_search_response({"papers": [{"title": "T"}]})["results"][0]["title"], "T")
        self.assertEqual(brave.parse_search_response({"results": [{"title": "t"}]})["results"][0]["title"], "t")
        self.assertEqual(brave.parse_search_response({"web": {"results": [None, {}]}})["results"], [])
        llm = brave.parse_llm_context_response(
            {"grounding": {"generic": [{}], "poi": {"title": "p"}, "map": [{"url": "http://x"}]}}
        )
        self.assertTrue(llm["results"])
        req = exa.build_search_request(
            "q",
            api_key="k",
            include_domains=["a.com"],
            exclude_domains=["b.com"],
            category="research paper",
            start_published="2020-01-01",
            end_published="2021-01-01",
            highlights=True,
            text=True,
        )
        self.assertIn(b"includeDomains", req.body or b"")
        self.assertEqual(exa.parse_search_response({"results": [None, {}]})["results"], [])
        self.assertEqual(exa.parse_contents_response("nope")["results"], [])
        with self.assertRaises(ProviderHttpError):
            firecrawl.reject_unsuccessful({"success": False, "error": "no"}, "scrape")
        self.assertIn(
            "markdown",
            firecrawl.parse_scrape_response({"data": {"content": "# x"}})["results"][0],
        )
        self.assertEqual(
            firecrawl.parse_search_response({"data": {"news": [{"url": "http://n", "markdown": "m"}]}})[
                "results"
            ][0]["url"],
            "http://n",
        )
        mapped = firecrawl.parse_map_response(
            {"data": {"links": ["http://a", None, {"url": "http://b", "title": "t", "description": "d"}]}}
        )
        self.assertEqual(len(mapped["results"]), 2)
        self.assertIsNone(papers._paper_record("x"))
        self.assertEqual(papers.parse_search_response({"results": "no"})["results"], [])
        self.assertEqual(
            papers.parse_read_response({"passages": ["p", None, {"text": "t", "score": 1}]})["results"][0]["text"],
            "p",
        )
        self.assertEqual(papers.parse_related_response("no")["results"], [])

    def test_reddit_exploitdb_sploitus_malpedia_x_edges(self) -> None:
        with self.assertRaises(ProviderHttpError):
            reddit.parse_token_response({})
        self.assertTrue(
            reddit._permalink_url({"permalink": "https://old.reddit.com/r/x"}).startswith("http")
        )
        self.assertTrue(reddit._permalink_url({"permalink": "r/x/comments/1"}).endswith("/r/x/comments/1"))
        self.assertEqual(reddit._permalink_url({"url": "https://example.com"}), "https://example.com")
        self.assertIsNone(reddit._post_record({}))
        parsed = reddit.parse_search_response(
            {"children": [{"title": "t", "permalink": "/r/x/comments/1"}], "results": []}
        )
        self.assertEqual(parsed["results"][0]["title"], "t")
        with self.assertRaises(ProviderHttpError):
            exploitdb.normalize_id("")
        with self.assertRaises(ProviderHttpError):
            exploitdb.normalize_id("nope")
        self.assertEqual(exploitdb.normalize_cve_query(None), None)
        with self.assertRaises(ProviderHttpError):
            exploitdb.normalize_cve_query("not-a-cve")
        self.assertEqual(exploitdb._format_cve(""), "")
        self.assertEqual(exploitdb._format_cve("CVE-1-2"), "CVE-1-2")
        self.assertEqual(exploitdb._format_cve("2021-1"), "CVE-2021-1")
        self.assertIsNone(exploitdb._normalize_tag(None))
        self.assertEqual(exploitdb._normalize_tag("12"), "12")
        self.assertEqual(exploitdb._normalize_tag("sqli"), exploitdb._TAG_BY_NAME["sqli"])
        self.assertEqual(exploitdb._normalize_tag("custom"), "custom")
        self.assertIsNone(exploitdb._normalize_category(None))
        self.assertEqual(exploitdb._normalize_category("9"), "9")
        self.assertEqual(exploitdb._normalize_category("Footholds"), "1")
        self.assertEqual(exploitdb._normalize_category("unknown"), "unknown")
        self.assertEqual(sploitus._normalize_type("hacktools"), "tools")
        self.assertEqual(sploitus._normalize_type("weird"), "exploits")
        with self.assertRaises(ProviderHttpError):
            sploitus.normalize_exploit_id("")
        self.assertEqual(sploitus.normalize_exploit_id("https://x/?id=ABC"), "ABC")
        self.assertEqual(sploitus.normalize_exploit_id("id=ZZ"), "ZZ")
        with self.assertRaises(ProviderHttpError):
            sploitus.normalize_cve("nope")
        with self.assertRaises(ProviderHttpError):
            sploitus.product_slug("")
        self.assertEqual(sploitus.product_slug("https://sploitus.com/product/foo/page/2"), "foo")
        with self.assertRaises(ProviderHttpError):
            sploitus.product_slug("/")
        ident, kind = sploitus._card_id_and_kind("/exploit?id=EDB-1")
        self.assertEqual(kind, "exploit")
        scored = sploitus._parse_cards(
            "<a class=vulnerability href=/cve/CVE-2020-1>"
            "<div class=vulnerability__title>T</div>"
            "<span class=vulnerability__meta-item>CVSS 9.8</span>"
            "<span class=vulnerability__meta-item>alice</span></a>"
        )
        self.assertEqual(scored[0]["score"], 9.8)
        self.assertEqual(scored[0]["author"], "alice")
        detailed = sploitus.parse_exploit_html(
            "<script type=application/ld+json>"
            '{"@type":"TechArticle","headline":"H"}</script>'
            "<span class=exploit__detail-label>Modified</span>"
            "<span class=exploit__detail-value>today</span>"
            "<span class=exploit__detail-label>Acme</span>"
            "<span class=exploit__detail-value>1.2</span>"
            "<div class=exploit__description-text>one</div>"
            "<div class=exploit__description-text>two</div>",
            exploit_id="E2",
        )
        self.assertIn("details", detailed["results"][0])
        self.assertIn("entry_point", detailed["results"][0])
        sploitus._next_path("<link href=/latest?page=2 rel=next>")
        ident, kind = sploitus._card_id_and_kind("https://x/cve/CVE-2021-1")
        self.assertEqual(kind, "cve")
        html = (
            "<script type=application/ld+json>not json</script>"
            "<script type=application/ld+json>"
            '{"@type":"TechArticle","headline":"H",'
            '"about":[{"identifier":"not-cve"},{"identifier":"CVE-2021-44228"}],'
            '"hasPart":{"programmingLanguage":"python"},'
            '"interactionStatistic":[{"userInteractionCount":3}],'
            '"url":"https://sploitus.com/exploit?id=X1"}'
            "</script>"
            '<div class="logo logo_remote"></div>'
            '<span class="cvss-number">not-a-float</span>'
        )
        parsed = sploitus.parse_exploit_html(html, exploit_id=None)
        self.assertEqual(parsed["results"][0]["title"], "H")
        with self.assertRaises(ProviderHttpError):
            sploitus._execute_html(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: (_ for _ in ()).throw(TimeoutError("t")),
                timeout=1,
            )
        with self.assertRaises(ProviderHttpError):
            sploitus._execute_html(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: HttpResponse(500, {}, b"err"),
                timeout=1,
            )
        self.assertEqual(malpedia._str_list("x"), [])
        req = malpedia.build_get_request("api/x")
        self.assertTrue(req.url.endswith("/api/x"))
        with self.assertRaises(ProviderHttpError):
            malpedia._execute_body(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: (_ for _ in ()).throw(OSError("e")),
                timeout=1,
            )
        with self.assertRaises(ProviderHttpError):
            malpedia._loads(b"")
        with self.assertRaises(ProviderHttpError):
            malpedia._loads(b"not-json")
        with self.assertRaises(ProviderHttpError):
            x.parse_tweet_ref("")
        self.assertEqual(
            x.parse_graphql_ops(
                "queryId:\"abc\",operationName:\"SearchTimeline\",operationType:\"query\","
                "metadata:{featureSwitches:['flag_one']}"
            )["SearchTimeline"].query_id,
            "abc",
        )
        self.assertIsNone(x._client_from_blob("no"))
        self.assertIsNone(x._client_from_blob({"version": 99}))
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": 1, "animation_key": "a"}))
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": "", "animation_key": "a"}))
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": "!!!!", "animation_key": "a"}))
        self.assertIsNone(
            x._client_from_blob(
                {"version": 1, "key_bytes": "YQ==", "animation_key": "a", "ops": ["bad"]}
            )
        )
        self.assertIsNone(
            x._read_disk_bootstrap("http://o", {"RESEARCH_CLI_CACHE_DIR": "/no/such"}, 1.0)
        )
        with tempfile.TemporaryDirectory() as raw:
            env = {"RESEARCH_CLI_CACHE_DIR": raw}
            path = x.bootstrap_cache_file("http://o", env)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("[]", encoding="utf-8")
            self.assertIsNone(x._read_disk_bootstrap("http://o", env, 1.0))
            path.write_text(json.dumps({"origin": "http://other", "saved_at": 1, "version": 1}), encoding="utf-8")
            self.assertIsNone(x._read_disk_bootstrap("http://o", env, 1.0))
            path.write_text(
                json.dumps({"origin": "http://o", "saved_at": "nope", "version": 1}),
                encoding="utf-8",
            )
            self.assertIsNone(x._read_disk_bootstrap("http://o", env, 1.0))
            client = x.XClient(tx=x_transaction.ClientTransaction(key_bytes=b"abc", animation_key="k"), ops={})
            with patch("pathlib.Path.mkdir", side_effect=OSError("disk")):
                x._write_disk_bootstrap("http://o", env, 1.0, client)
        with self.assertRaises(ProviderHttpError):
            x._execute_text(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: (_ for _ in ()).throw(TimeoutError("t")),
                timeout=1,
            )
        self.assertEqual(x._expanded_urls({}), [])
        self.assertEqual(x._expanded_urls({"entities": {"urls": "no"}}), [])
        self.assertIsNone(x._best_video_url({"video_info": {"variants": "no"}}))
        self.assertIsNone(x._best_video_url({"video_info": {"variants": [None]}}))
        self.assertEqual(
            x._media_items({}, {"extended_entities": {"media": [None]}}), []
        )
        self.assertIsNone(x._unwrap_tweet("no"))
        self.assertIsNone(x._unwrap_tweet({"__typename": "Other", "legacy": {}}))
        tweets, _cursors = x.parse_timeline("no")
        self.assertEqual(tweets, [])
        self.assertEqual(x.project_payload({"results": []}, ["  ", ""]), {"results": []})
        x_transaction._cubic_value([0.2, 0.1, 1, 1], -1.0)
        x_transaction._cubic_value([0, 0, 0.5, 1], -1.0)
        x_transaction._cubic_value([0, 1, 0.5, 1], -0.5)
        x_transaction._cubic_value([0, 0, 0, 0], -1.0)
        x_transaction._cubic_value([0, 0, 0.5, 0.5], 2.0)
        x_transaction._cubic_value([0.2, 0.1, 1, 1], 2.0)
        x_transaction._cubic_value([0.5, 0, 1, 1], 2.0)
        x_transaction._cubic_value([1, 1, 1, 1], 2.0)
        self.assertEqual(x_transaction._float_to_hex(4.0), "4")
        with self.assertRaises(ProviderHttpError):
            x_transaction.extract_ondemand_hash(',12:"ondemand.s"')
        with self.assertRaises(ProviderHttpError):
            x_transaction.extract_frames("id=\"loading-x-anim-0\"")
        with self.assertRaises(ProviderHttpError):
            x_transaction._generate_2d_array('id="x"</path><path d="M 1"')

    def test_cli_unknown_provider_ops_and_schedule(self) -> None:
        ns = argparse.Namespace
        with self.assertRaises(ValueError):
            _dispatch_firecrawl(ns(operation="crawl", live=False, max_age=None, no_main_content=False, formats="markdown"), {"FIRECRAWL_API_KEY": "k"}, None, 1)
        with self.assertRaises(ValueError):
            _dispatch_reddit(ns(operation="user"), {"REDDIT_CLIENT_ID": "a", "REDDIT_CLIENT_SECRET": "b"}, None, 1)
        with self.assertRaises(ValueError):
            _dispatch_sploitus(ns(operation="rss"), {}, None, 1)
        with self.assertRaises(ValueError):
            _dispatch_exploitdb(ns(operation="login"), {}, None, 1)
        with self.assertRaises(ValueError):
            _dispatch_malpedia(ns(operation="sample"), {}, None, 1)
        with self.assertRaises(ValueError):
            _dispatch_x(ns(operation="likes"), {"X_AUTH_TOKEN": "a", "X_CT0": "b"}, None, 1)
        self.assertEqual(help_topic_payload(None)["topics"], ["install", "keys"])
        _schedule_update({}, lambda _e: (_ for _ in ()).throw(RuntimeError("x")))
        self.assertIsNone(_csv(""))
        with patch.object(sys, "argv", ["research-cli", "help"]):
            code = main(
                None,
                environ={"RESEARCH_CLI_NO_UPDATE": "1"},
                stdout=io.StringIO(),
                spawn_update=lambda _e: None,
            )
            self.assertEqual(code, 0)


class RemainingLineTests(unittest.TestCase):
    def test_origin_ssl_keys_exa(self) -> None:
        from research_cli.cli import _origin as origin_of

        args = argparse.Namespace(base_url="http://fixture")
        self.assertEqual(origin_of(args, {}, "https://x.com"), "http://fixture")
        with patch.dict(os.environ, {"SSL_CERT_FILE": "", "SSL_CERT_DIR": ""}, clear=False):
            os.environ.pop("SSL_CERT_FILE", None)
            os.environ.pop("SSL_CERT_DIR", None)
            with patch.object(sys, "frozen", True, create=True):
                with patch("research_cli.http.Path.is_file", return_value=False):
                    ssl_context()
        class HomePath(type(Path.home())):
            @classmethod
            def home(cls):
                return cls("/Users/me")

        from pathlib import PurePosixPath

        class HomePure(PurePosixPath):
            @classmethod
            def home(cls):
                return cls("/Users/me")

        with patch("research_cli.keys.os.name", "nt"), patch(
            "research_cli.keys.Path", HomePure
        ):
            path = default_env_path({})
            self.assertIn("AppData", str(path))
        self.assertEqual(exa.parse_search_response({"results": "nope"})["results"], [])

    def test_firecrawl_papers_reddit_malpedia_update(self) -> None:
        firecrawl.parse_scrape_response("nope")
        firecrawl.parse_search_response(["http://skip", {"url": ""}, None])
        firecrawl.parse_map_response({"links": None})
        firecrawl.parse_map_response({"links": [{"title": "t"}]})
        papers.parse_read_response({"paper": {"passages": [None, {"content": ""}]}})
        papers.parse_read_response("nope")
        self.assertEqual(
            reddit.parse_search_response({"results": [None, {"title": "t"}]})["results"][0]["title"],
            "t",
        )
        with self.assertRaises(ProviderHttpError):
            reddit.parse_thread_ref("")
        self.assertEqual(reddit.parse_thread_ref("https://reddit.com/r/x/comments/t3_abc/title"), "abc")
        self.assertEqual(reddit.parse_thread_ref("t3_zz"), "zz")
        with self.assertRaises(ProviderHttpError):
            reddit.parse_thread_ref("https://reddit.com/r/x/")
        reddit.parse_thread_response({"children": [None]})
        reddit.parse_thread_response(["not-listing", {"kind": "t1", "data": {"body": "hi", "author": "a"}}])
        reddit._listing_children(["a"])
        reddit._listing_children("x")
        reddit._comment_record({}, depth=0)
        reddit._collect_comments([None, {"kind": "more", "data": {}}], [], depth=0)
        with self.assertRaises(ProviderHttpError):
            reddit.build_subreddit_request("", access_token="t")
        with self.assertRaises(ProviderHttpError):
            malpedia.yara_dump(transport=lambda r: HttpResponse(200, {}, b"x"))
        with self.assertRaises(ProviderHttpError):
            malpedia.yara_after("nope")
        with self.assertRaises(ProviderHttpError):
            malpedia.bib(family="a", actor="b")
        with self.assertRaises(ProviderHttpError):
            malpedia.sample("zz", token="t")
        with self.assertRaises(ProviderHttpError):
            malpedia.download("zz", token="t")
        with self.assertRaises(ProviderHttpError):
            malpedia._execute_body(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: HttpResponse(403, {}, b"no"),
                timeout=1,
            )
        self.assertEqual(malpedia.normalize_tlp("tlp_white"), "tlp_white")
        malpedia._find_hits([None, {"name": ""}])
        with tempfile.TemporaryDirectory() as raw:
            env = {"RESEARCH_CLI_CACHE_DIR": raw}
            malpedia.actors(
                output=raw,
                transport=lambda _r: HttpResponse(200, {}, b"[]"),
            )
            malpedia.actors(
                full=True,
                limit=1,
                transport=lambda _r: HttpResponse(200, {}, json.dumps({"a": 1, "b": 2}).encode()),
            )
            malpedia.actors(
                limit=1,
                transport=lambda _r: HttpResponse(200, {}, json.dumps(["a", "b"]).encode()),
            )
            malpedia.yara_after(
                "2026-01-01",
                output=raw,
                transport=lambda _r: HttpResponse(200, {}, b"{}"),
            )
        from research_cli.update import pip_hint, run_self_update, wait_for_pid, MAX_ASSET_BYTES

        self.assertIn("ErcinDedeoglu", pip_hint({"RESEARCH_CLI_REPO": "not valid"}))
        wait_for_pid(1, timeout=0.0, running=lambda _p: True, clock=lambda: 10.0, sleeper=lambda _s: None)
        with self.assertRaises(UpdateError):
            run_self_update(
                environ={"RESEARCH_CLI_NO_UPDATE": "1"},
                install=Install("frozen", None, "Darwin", "arm64"),
            )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "bin"
            path.write_bytes(b"old")
            with self.assertRaises(UpdateError):
                run_self_update(
                    environ={"RESEARCH_CLI_CACHE_DIR": raw},
                    install=Install("frozen", path, "Darwin", "arm64"),
                    transport=lambda _r: HttpResponse(200, {}, json.dumps({"tag_name": "", "assets": []}).encode()),
                )
            huge = {"tag_name": "v9.9.9", "assets": [{"name": "research-cli-Darwin-arm64", "browser_download_url": "https://github.com/x", "size": MAX_ASSET_BYTES + 1}]}
            with self.assertRaises(UpdateError):
                run_self_update(
                    environ={"RESEARCH_CLI_CACHE_DIR": raw},
                    install=Install("frozen", path, "Darwin", "arm64"),
                    current_version="0.0.1",
                    transport=lambda _r: HttpResponse(200, {}, json.dumps(huge).encode()),
                )
        handle = MagicMock()
        handle.close.side_effect = OSError("close")
        with patch("research_cli.update.cache_dir", return_value=Path("/tmp")), patch(
            "pathlib.Path.open", return_value=handle
        ), patch("pathlib.Path.mkdir"):
            spawn_background_update(
                environ={},
                install=Install("frozen", Path("/tmp/bin"), "Darwin", "arm64"),
                popen=lambda *a, **k: MagicMock(),
            )

    def test_exploitdb_x_helpers(self) -> None:
        self.assertEqual(
            exploitdb.filename_from_headers(
                {"content-disposition": "attachment; filename*=utf-8''foo%20bar.py"},
                "1",
            ),
            "foo bar.py",
        )
        self.assertEqual(
            exploitdb.filename_from_headers(
                {"content-disposition": "attachment; filename=plain.bin"},
                "1",
            ),
            "plain.bin",
        )
        self.assertTrue(exploitdb.filename_from_headers({}, "9").startswith("9"))
        self.assertEqual(
            exploitdb.filename_from_headers(
                {"content-disposition": 'attachment; filename="quoted.bin"'},
                "1",
            ),
            "quoted.bin",
        )
        exploitdb._datatables_params("/unknown")
        binary = exploitdb.raw(
            "50592",
            transport=lambda _r: HttpResponse(
                200, {"content-type": "application/octet-stream"}, b"\x00\x01"
            ),
        )
        self.assertIn("download", binary)
        row = {
            "id": "1",
            "description": "<b>title</b>",
            "author_id": [1, "alice"],
            "code": [None, {"code_type": "cve", "code": "2021-1"}],
            "tags": [{"title": "xss"}, "rce", None],
        }
        parsed = exploitdb.parse_exploit_row(row, origin="https://www.exploit-db.com")
        self.assertEqual(parsed["title"], "title")
        exploitdb.parse_table_payload("nope", kind="exploit", origin="https://x")
        with self.assertRaises(ProviderHttpError):
            exploitdb._execute_body(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: (_ for _ in ()).throw(TimeoutError("t")),
                timeout=1,
            )
        html = '<meta name="description" content="Hub title"><div class="info"></div>'
        hub = exploitdb._parse_hub(
            html, ident="1", kind="exploit", origin="https://www.exploit-db.com"
        )
        self.assertEqual(hub.get("title"), "Hub title")
        firecrawl.build_search_request(
            "q", api_key="k", exclude_domains=["a.com"]
        )
        x.parse_tweet_ref("/2069347283918000383")
        self.assertEqual(x._user_core({}), {})
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": "YQ==", "animation_key": "a", "extra": "nope"}))
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": "YQ==", "animation_key": "a", "keyword": 1}))
        self.assertIsNone(
            x._client_from_blob(
                {"version": 1, "key_bytes": "YQ==", "animation_key": "a", "ops": {"SearchTimeline": "no"}}
            )
        )
        self.assertIsNone(
            x._client_from_blob(
                {
                    "version": 1,
                    "key_bytes": "YQ==",
                    "animation_key": "a",
                    "ops": {"SearchTimeline": {"query_id": ""}},
                }
            )
        )
        self.assertIsNone(
            x._client_from_blob(
                {
                    "version": 1,
                    "key_bytes": "YQ==",
                    "animation_key": "a",
                    "ops": {"SearchTimeline": {"query_id": "abc", "features": ["x"]}},
                }
            )
        )
        with self.assertRaises(ProviderHttpError):
            x._execute_text(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: HttpResponse(200, {}, b"  "),
                timeout=1,
            )
        with self.assertRaises(ProviderHttpError):
            x._query_id({}, "UnknownOp")
        self.assertIsNone(x._user_record("no"))
        self.assertIsNone(x._user_record({"__typename": "UserUnavailable"}))
        self.assertIsNone(x._user_record({"core": {}, "legacy": {}}))
        rec = x._user_record(
            {
                "rest_id": "1",
                "legacy": {"screen_name": "u", "description": "bio"},
            }
        )
        self.assertEqual(rec["username"], "u")
        wrapped = x._unwrap_tweet({"legacy": {"full_text": "hi", "id_str": "1"}})
        self.assertIsNotNone(wrapped)
        self.assertIsNone(x._tweet_record(None))
        x.project_payload({"tweet": {"id": "1", "text": "t"}, "results": [{"id": "1"}]}, ["id"])
        x.project_payload({"results": [{"id": "1", "retweet": {"id": "2"}}]}, ["id", "retweet"])
        x.parse_timeline({"data": {"foo": 1}})
        self.assertEqual(x._expanded_urls({"entities": {"urls": [None, {"url": ""}]}}), [])
        self.assertIsNone(x._view_count({}))
        x._best_video_url({"video_info": {"variants": [{"url": "http://x", "bitrate": "no"}]}})
        x._retweet_source("no", {})
        x._retweet_source({}, {"retweeted_status": {"legacy": {"full_text": "rt"}}})
        x._media_items({}, {"extended_entities": {"media": [{"type": "photo"}]}})
        with self.assertRaises(ProviderHttpError):
            x_transaction.animate([1, 2, 3], 0.5)
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(["f"] * 4, 0, b"ab", [1])
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(["f"] * 4, 99, b"abcdef", [1])
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(["f"] * 4, 0, b"abcdef", [99])
        with self.assertRaises(ProviderHttpError):
            x_transaction.ClientTransaction.from_documents(
                '<meta name="twitter-site-verification" content="%%%">', "x"
            )
        x_transaction._float_to_hex(0.5)
        x_transaction._cubic_value([0.1, 0.2, 0.9, 0.8], 0.5)


class FinalGapTests(unittest.TestCase):
    def test_sploitus_search_html_and_hubs(self) -> None:
        sploitus.build_product_request("wordpress", page=2)
        self.assertIsNone(sploitus._item("x", include_source=False))
        self.assertIsNone(sploitus._item({}, include_source=False))
        hit = sploitus._item(
            {"id": "1", "cve_string": "CVE-1", "source": "code"},
            include_source=True,
        )
        self.assertEqual(hit["cve"], ["CVE-1"])
        parsed = sploitus.parse_search_response({"exploits": [None], "exploits_total": "3"})
        self.assertEqual(parsed["total"], 3)
        empty = sploitus.search("q", limit=0)
        self.assertEqual(empty["results"], [])
        ident, kind = sploitus._card_id_and_kind("https://sploitus.com/exploit?foo=1&id=Z9")
        self.assertEqual(kind, "exploit")
        sploitus._parse_cards(
            "<a class=vulnerability href=/cve/CVE-2020-1>"
            "<div class=vulnerability__title>T</div>"
            "<span class=vulnerability__count>1</span>"
            "<span class=vulnerability__meta-item>CVSS x</span></a>"
        )
        html = (
            "<script type=application/ld+json>"
            '{"@type":"TechArticle","headline":"H","description":"D",'
            '"about":{"identifier":"not-cve"},'
            '"dateModified":"2020-01-01"}'
            "</script>"
            '<div class="exploit-details"><span>Reporter</span><span>bob</span></div>'
            '<div class="exploit-details"><span>Parameter</span><span>id</span></div>'
            '<div class="exploit-details"><span>Widget</span><span>1.0</span></div>'
            '<span class="cvss-number">abc</span>'
            '<span class="epss-value">0.1</span><span class="epss-of">of 1</span>'
        )
        rec = sploitus.parse_exploit_html(html, exploit_id="E1")
        self.assertEqual(rec["results"][0]["id"], "E1")
        with self.assertRaises(ProviderHttpError):
            sploitus.parse_exploit_html("<html></html>", exploit_id=None)
        cve_html = (
            "<script type=application/ld+json>"
            '{"@type":"CollectionPage","about":{"identifier":"CVE-2021-1","description":"d","url":"https://nvd"}}'
            "</script>"
        )
        sploitus.parse_cve_html(cve_html, cve_id=None)
        sploitus.parse_cve_html('<div class="description">plain desc</div>', cve_id="CVE-2021-1")
        sploitus.parse_product_html("<html></html>", name="wordpress")
        sploitus.parse_home_html('<section class="card"><h2 class="card__title">Empty</h2></section>')
        pages = []

        def send(request):
            pages.append(request.url)
            if len(pages) == 1:
                return HttpResponse(200, {}, b"<html>page1</html>")
            return HttpResponse(200, {}, b"<html>page2</html>")

        sploitus._collect_hub_pages(
            sploitus.build_cve_request("CVE-2021-44228"),
            parse=lambda _h: {"results": []},
            limit=10,
            origin="https://sploitus.com",
            transport=send,
            timeout=1,
        )
        sploitus._collect_hub_pages(
            sploitus.build_cve_request("CVE-2021-44228"),
            parse=lambda _h: {"results": [{"id": "1"}]},
            limit=0,
            origin="https://sploitus.com",
            transport=lambda _r: HttpResponse(200, {}, b"<html></html>"),
            timeout=1,
        )
        sploitus.search(
            "q",
            limit=10,
            transport=lambda _r: HttpResponse(200, {}, json.dumps({"exploits": []}).encode()),
        )

    def test_x_rewrite_project_and_update_windowsish(self) -> None:
        self.assertTrue(
            x._rewrite_asset_url("/responsive-web/client-web/main.x.js", "http://fixture").endswith(
                "/main.x.js"
            )
        )
        with self.assertRaises(ProviderHttpError):
            x._graphql_json(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: HttpResponse(404, {}, b"missing"),
                timeout=1,
            )
        from fixtures import X_HOME_HTML, X_ONDEMAND_JS, X_MAIN_JS, X_SEARCH_PAYLOAD

        class Seq:
            def __init__(self, bodies):
                self.bodies = list(bodies)
                self.i = 0

            def __call__(self, request):
                body = self.bodies[self.i]
                self.i += 1
                if isinstance(body, dict):
                    return HttpResponse(200, {}, json.dumps(body).encode())
                return HttpResponse(200, {}, body.encode() if isinstance(body, str) else body)

        home = X_HOME_HTML.replace(
            'src="https://abs.twimg.com/responsive-web/client-web/main.fixturea.js"',
            'src="/responsive-web/client-web/main.fixturea.js"',
        )
        seq = Seq([home, X_ONDEMAND_JS, X_MAIN_JS, X_SEARCH_PAYLOAD])
        out = x.search("q", auth_token="a", ct0="b", origin="http://127.0.0.1", transport=seq)
        self.assertEqual(out["provider"], "x")
        self.assertIsNone(x._in_reply_to({}))
        x._best_video_url(
            {"video_info": {"variants": [{"content_type": "video/mp4", "url": "http://v", "bitrate": "high"}]}}
        )
        x.project_payload({"replies": [{"id": "1", "text": "t"}]}, ["id"])
        x._tweet_record({"__typename": "Unknown"})
        rec = x._project_record({"id": "1", "retweet": {"id": "2", "text": "x"}}, ["id", "retweet"])
        self.assertIn("retweet", rec)
        pid_is_running(os.getpid())
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "bin"
            target.write_bytes(b"old")
            old = target.parent / f".{target.name}.old"
            with patch("pathlib.Path.unlink", side_effect=OSError("busy")):
                replace_executable(target, b"new", windows=True)
            target.write_bytes(b"old")

            def boom_replace(src, dst):
                raise OSError("inuse")

            with patch("research_cli.update.os.replace", side_effect=boom_replace):
                with self.assertRaises(OSError):
                    replace_executable(target, b"new", windows=True)
            env = {"RESEARCH_CLI_CACHE_DIR": raw}
            with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir")):
                spawn_background_update(
                    environ=env,
                    install=Install("frozen", Path(raw) / "b", "Darwin", "arm64"),
                    popen=lambda *a, **k: MagicMock(),
                )
            captured: dict[str, object] = {}

            def popen(*_a, **kwargs):
                captured.update(kwargs)
                return MagicMock()

            cache = Path(raw)
            with patch("research_cli.update.os.name", "posix"):
                spawn_background_update(
                    environ=env,
                    install=Install("frozen", Path(raw) / "b", "Darwin", "arm64"),
                    popen=popen,
                )
            msvcrt = MagicMock()
            with patch.dict("sys.modules", {"msvcrt": msvcrt}), patch(
                "research_cli.update.os.name", "nt"
            ), patch("research_cli.update.cache_dir", return_value=cache):
                handle = acquire_update_lock(env, blocking=True)
                if handle:
                    handle.close()
            with self.assertRaises(UpdateError):
                run_self_update(
                    environ=env,
                    install=Install("zipapp", None, "Darwin", "arm64"),
                )
        malpedia.parse_yara({"white": "nope"})
        malpedia.parse_samples([None, {"sha256": "abc"}], family="win.emotet")
        with tempfile.TemporaryDirectory() as raw:
            malpedia.misp(
                output=raw,
                transport=lambda _r: HttpResponse(200, {}, b"{}"),
            )
            malpedia.references(
                output=raw,
                transport=lambda _r: HttpResponse(200, {}, b"{}"),
            )
        reddit.parse_thread_ref("t3_only")
        reddit._listing_children({"children": [1]})
        reddit.parse_thread_response({"post": {"children": ["x"]}})
        exploitdb._author_name({"author_id": [1]})
        exploitdb._cves({"code": [{"code_type": "osvdb", "code": "1"}]})
        exploitdb._parse_hub(
            '<meta name="author" content="bob">',
            ident="1",
            kind="exploit",
            origin="https://www.exploit-db.com",
        )
        with self.assertRaises(ProviderHttpError):
            exploitdb._execute_body(
                HttpRequest("GET", "http://x"),
                transport=lambda _r: HttpResponse(500, {}, b"err"),
                timeout=1,
            )
        x_transaction._float_to_hex(0.0625)
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(["f"] * 4, 0, b"abcdefg", [0, 99])


class LastSixtyTests(unittest.TestCase):
    def test_remaining_provider_and_update_lines(self) -> None:
        from fixtures import X_HOME_HTML
        from research_cli.update import _install_latest, MAX_ASSET_BYTES

        exploitdb.search(
            "q",
            transport=lambda _r: HttpResponse(
                200, {}, json.dumps({"recordsTotal": 0, "data": []}).encode()
            ),
        )
        with self.assertRaises(ProviderHttpError):
            malpedia.normalize_tlp("tlp_purple")
        self.assertEqual(reddit.parse_thread_ref("T3_abcd"), "abcd")
        self.assertEqual(reddit._listing_children({"x": 1}), [])
        reddit.parse_thread_response(
            {"post": {"data": {"children": [{"kind": "t3", "data": "nope"}]}}}
        )
        self.assertIsNone(x._client_from_blob({"version": 1, "key_bytes": "@@@@", "animation_key": "a"}))
        self.assertIsNone(
            x._best_video_url({"video_info": {"variants": [{"content_type": "video/mp4"}]}})
        )
        self.assertIsNone(x._view_count({"views": {"count": None}}))
        self.assertIsNone(x._view_count({"views": {"count": "nope"}}))
        self.assertIsNone(x._tweet_record({"__typename": "Tweet", "legacy": {}}))
        self.assertEqual(x._project_record("keep", ["id"]), "keep")
        frames = x_transaction.extract_frames(X_HOME_HTML)
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(frames, 99, b"abcdef", [0])
        with self.assertRaises(ProviderHttpError):
            x_transaction.calculate_animation_key(frames, 0, b"abcdef", [99])
        with self.assertRaises(ProviderHttpError):
            x_transaction.ClientTransaction.from_documents(
                '<meta name="twitter-site-verification" content="@@@@"/>'
                + X_HOME_HTML,
                "(a[7], 16),(a[37], 16)",
            )
        x_transaction._cubic_value([0.0, 0.0, 1.0, 1.0], 0.33)
        chosen = x_transaction._generate_2d_array(frames[0])
        x_transaction.animate(chosen[0], 0.25)
        with self.assertRaises(UpdateError):
            _install_latest(
                environ={},
                transport=lambda _r: HttpResponse(
                    200,
                    {},
                    json.dumps(
                        {
                            "tag_name": "v9.9.9",
                            "assets": [
                                {
                                    "name": "research-cli-Darwin-arm64",
                                    "browser_download_url": "https://github.com/x",
                                    "size": 10,
                                }
                            ],
                        }
                    ).encode(),
                ),
                install=Install("frozen", None, "Darwin", "arm64"),
                version="0.1.0",
                timeout=1,
            )
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "bin"
            target.write_bytes(b"old")
            calls = {"n": 0}

            def flaky(src, dst):
                calls["n"] += 1
                if calls["n"] == 1:
                    Path(dst).write_bytes(Path(src).read_bytes() if False else b"x")
                    return
                raise OSError("tmp")

            # first replace target->old succeeds via real os.replace; patch after exists
            real_replace = os.replace

            def mixed(src, dst):
                if str(dst).endswith(".old"):
                    return real_replace(src, dst)
                raise OSError("tmp-to-target")

            def mixed2(src, dst):
                raise OSError("all")

            target.write_bytes(b"old")
            with patch("research_cli.update.os.replace", mixed):
                with patch("research_cli.update.os.replace", mixed) as _:
                    pass
            target.write_bytes(b"old")
            with patch("research_cli.update.os.replace", side_effect=[None, OSError("t"), OSError("r")]):
                with self.assertRaises(OSError):
                    replace_executable(target, b"new", windows=True)
        captured: dict[str, object] = {}

        def popen(*_a, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        with tempfile.TemporaryDirectory() as raw:
            frozen_bin = Path(raw) / "b"
            cache_root = Path(raw)
            with patch("research_cli.update.os.name", "nt"), patch(
                "research_cli.update.cache_dir", return_value=cache_root
            ):
                spawn_background_update(
                    environ={"RESEARCH_CLI_CACHE_DIR": raw},
                    install=Install("frozen", frozen_bin, "Windows", "x86_64"),
                    popen=popen,
                )
            self.assertIn("creationflags", captured)
            fake_ct = MagicMock()
            fake_ct.windll.kernel32.OpenProcess.return_value = 0
            with patch("research_cli.update.os.name", "nt"), patch.dict(
                sys.modules, {"ctypes": fake_ct}
            ):
                self.assertFalse(pid_is_running(5))
            fake_ct.windll.kernel32.OpenProcess.return_value = 3
            with patch("research_cli.update.os.name", "nt"), patch.dict(
                sys.modules, {"ctypes": fake_ct}
            ):
                self.assertTrue(pid_is_running(5))
        sploitus.search(
            "q",
            limit=25,
            transport=lambda _r: HttpResponse(
                200,
                {},
                json.dumps({"exploits": [{"id": str(i)} for i in range(10)], "exploits_total": 10}).encode(),
            ),
        )
        sploitus._next_path("<link href=/latest/page/2 rel=next>")
        sploitus._next_path("<a class=pagination__link href=page2 rel=next>")
        sploitus.product(
            "wordpress",
            limit=1,
            transport=lambda _r: HttpResponse(
                200,
                {},
                b"<html><link href=/product/wordpress/page/2 rel=next></html>",
            ),
        )


class LastThirtyTests(unittest.TestCase):
    def test_reddit_x_sploitus_update_last_lines(self) -> None:
        from fixtures import X_HOME_HTML, X_ONDEMAND_JS, X_VERIFY_KEY
        from pathlib import PurePosixPath

        self.assertEqual(reddit.parse_thread_ref("/t3_zzzz"), "zzzz")
        sploitus._parse_cards(
            "<a class=vulnerability href=/cve/CVE-2020-1>"
            "<div class=vulnerability__title>T</div>"
            "<span class=vulnerability__meta-item>CVSS 9.8</span></a>"
        )
        sploitus._next_path('<link href="" rel=next>')
        html = (
            "<script type=application/ld+json>"
            '{"@type":"TechArticle","headline":"H"}'
            "</script>"
            "<span class=exploit__detail-label>Modified</span>"
            "<span class=exploit__detail-value>today</span>"
            "<span class=exploit__detail-label>Last seen</span>"
            "<span class=exploit__detail-value>now</span>"
            "<span class=exploit__component-label>AV</span>"
            "<span class=exploit__component-value>N</span>"
            "<span class=exploit__cvss-number>n/a</span>"
            "<span class=exploit__cvss-version>3.1</span>"
            "<span class=exploit__epss-value>0.2</span>"
            "<span class=exploit__epss-of>note</span>"
            "<div class=exploit__description-text>desc one</div>"
            "data-lang=ruby "
        )
        sploitus.parse_exploit_html(html, exploit_id="E1")
        sploitus._card_id_and_kind("/other")
        sploitus._card_id_and_kind("/exploit?foo=1#id=ABC")
        sploitus._next_path("<link href= rel=next>")
        sploitus._next_path("<link href=latest/page/2 rel=next>")
        sploitus.parse_home_html("<section class=card><h2 class=card__title>X</h2></section>")
        sploitus.parse_cve_html(
            '<p class="vulnerability__description">fallback</p>',
            cve_id="CVE-2021-1",
        )
        self.assertIsNone(
            x._client_from_blob({"version": 1, "key_bytes": "abc", "animation_key": "a"})
        )
        self.assertIsNone(x._tweet_record({"__typename": "Tweet"}))
        broken = X_HOME_HTML.replace(X_VERIFY_KEY, "abc")
        with self.assertRaises(ProviderHttpError):
            x_transaction.ClientTransaction.from_documents(broken, X_ONDEMAND_JS)
        from research_cli.providers.sploitus import _DETAIL_PAIR_RE

        pairs = sploitus._pairs(
            _DETAIL_PAIR_RE,
            "<span class=exploit__detail-label>Modified</span>"
            "<span class=exploit__detail-value>today</span>"
            "<span class=exploit__detail-label>Widget</span>"
            "<span class=exploit__detail-value>1.0</span>",
        )
        self.assertTrue(pairs)
        x_transaction._cubic_value([0.05, 0.9, 0.1, 0.8], 0.42)
        x_transaction._float_to_hex(0.00390625)
        for step in range(1, 20):
            x_transaction._cubic_value([0.01, 0.99, 0.02, 0.2], step / 20)
        from fixtures import X_HOME_HTML as _home

        row = x_transaction._generate_2d_array(x_transaction.extract_frames(_home)[0])[0]
        orig_hex = x_transaction._float_to_hex

        def dotted(numf: float) -> str:
            text = orig_hex(numf)
            return text.replace("0.", ".", 1) if text.startswith("0.") else text

        with patch.object(x_transaction, "_float_to_hex", dotted):
            x_transaction.animate(row, 0.4)
        class HomePure(PurePosixPath):
            @classmethod
            def home(cls):
                return cls("/Users/me")

        with patch("research_cli.update.os.name", "nt"), patch(
            "research_cli.update.Path", HomePure
        ):
            path = cache_dir({})
            self.assertIn("AppData", str(path))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "bin"
            target.write_bytes(b"old")
            state = {"n": 0}

            def mixed(src, dst):
                state["n"] += 1
                if state["n"] == 1:
                    Path(dst).write_bytes(Path(src).read_bytes())
                    Path(src).unlink()
                    return
                raise OSError("fail")

            with patch("research_cli.update.os.replace", mixed):
                with self.assertRaises(OSError):
                    replace_executable(target, b"new", windows=True)


if __name__ == "__main__":
    unittest.main()




