"""X (Twitter) GraphQL search/thread. Cookie session + generated tid.

Guest search is 404. Logged-in web client: GET /i/api/graphql/{queryId}/SearchTimeline
and TweetDetail, public web Bearer, ct0 CSRF, auth_token cookie, and
x-client-transaction-id from homepage SVG + ondemand.s.js.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse

from research_cli.errors import MissingKeyError, ProviderHttpError
from research_cli.http import (
    HttpRequest,
    Transport,
    execute_json,
    join_url,
    urllib_transport,
    with_query,
)
from research_cli.providers.x_transaction import (
    EXTRA_BYTE,
    KEYWORD,
    ClientTransaction,
    extract_main_script_url,
    extract_ondemand_hash,
    ondemand_url,
)
from research_cli.update import cache_dir

DEFAULT_ORIGIN = "https://x.com"
ASSET_ORIGIN = "https://abs.twimg.com"
HOME_PATH = "/home"
# Public web client token shipped in the JS bundle (not a user secret).
WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs="
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)
PRODUCTS = {
    "latest": "Latest",
    "top": "Top",
    "people": "People",
    "media": "Photos",
}
# Captured from the live web client 2026-08-28. Unknown flags default True.
DEFAULT_FEATURES: dict[str, bool] = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
FALLBACK_QUERY_IDS = {
    "SearchTimeline": "hyPfJYJ_XAtDYoslQc-Rgg",
    "TweetDetail": "XMOz5h24KAZ86qKffKTLdQ",
}
_OP_RE = re.compile(
    r'queryId:"([A-Za-z0-9_-]+)",operationName:"(SearchTimeline|TweetDetail)"'
    r',operationType:"query",metadata:\{featureSwitches:(\[[^\]]*\])'
)
_STATUS_RE = re.compile(r"(?:/status/|/i/web/status/)(\d+)")
TWEET_FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withGrokAnalyze": False,
    "withDisallowedReplyControls": False,
}
BOOTSTRAP_TTL_S = 3600.0
BOOTSTRAP_CACHE_VERSION = 1
COOKIE_EXPIRED = "x cookies expired; set X_AUTH_TOKEN and X_CT0"


@dataclass(frozen=True)
class GraphQLOp:
    query_id: str
    features: dict[str, bool]


@dataclass
class XClient:
    tx: ClientTransaction
    ops: dict[str, GraphQLOp]


def bootstrap_cache_file(
    origin: str, environ: Mapping[str, str] | None = None
) -> Path:
    env = os.environ if environ is None else environ
    digest = hashlib.sha256(origin.rstrip("/").encode("utf-8")).hexdigest()[:16]
    return cache_dir(env) / "x-bootstrap" / f"{digest}.json"


def _client_to_blob(origin: str, saved_at: float, client: XClient) -> dict[str, Any]:
    return {
        "version": BOOTSTRAP_CACHE_VERSION,
        "origin": origin.rstrip("/"),
        "saved_at": saved_at,
        "key_bytes": base64.b64encode(client.tx.key_bytes).decode("ascii"),
        "animation_key": client.tx.animation_key,
        "keyword": client.tx.keyword,
        "extra": client.tx.extra,
        "ops": {
            name: {"query_id": op.query_id, "features": dict(op.features)}
            for name, op in client.ops.items()
        },
    }


def _client_from_blob(data: Any) -> XClient | None:
    if not isinstance(data, dict):
        return None
    if data.get("version") != BOOTSTRAP_CACHE_VERSION:
        return None
    key_b64 = data.get("key_bytes")
    animation_key = data.get("animation_key")
    if not isinstance(key_b64, str) or not isinstance(animation_key, str):
        return None
    if not key_b64 or not animation_key:
        return None
    try:
        key_bytes = base64.b64decode(key_b64)
    except (ValueError, TypeError):
        return None
    if not key_bytes:
        return None
    extra_raw = data.get("extra", EXTRA_BYTE)
    try:
        extra = int(extra_raw)
    except (TypeError, ValueError):
        return None
    keyword = data.get("keyword") or KEYWORD
    if not isinstance(keyword, str):
        return None
    ops: dict[str, GraphQLOp] = {}
    raw_ops = data.get("ops") or {}
    if not isinstance(raw_ops, dict):
        return None
    for name, raw in raw_ops.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            return None
        query_id = raw.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            return None
        features_raw = raw.get("features") or {}
        if not isinstance(features_raw, dict):
            return None
        features = {str(flag): bool(value) for flag, value in features_raw.items()}
        ops[name] = GraphQLOp(query_id=query_id, features=features)
    return XClient(
        tx=ClientTransaction(
            key_bytes=key_bytes,
            animation_key=animation_key,
            keyword=keyword,
            extra=extra,
        ),
        ops=ops,
    )


def _read_disk_bootstrap(
    origin: str,
    environ: Mapping[str, str],
    now: float,
) -> XClient | None:
    path = bootstrap_cache_file(origin, environ)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("origin") != origin.rstrip("/"):
        return None
    try:
        saved_at = float(data.get("saved_at"))
    except (TypeError, ValueError):
        return None
    if now - saved_at >= BOOTSTRAP_TTL_S:
        return None
    return _client_from_blob(data)


def _write_disk_bootstrap(
    origin: str,
    environ: Mapping[str, str],
    now: float,
    client: XClient,
) -> None:
    path = bootstrap_cache_file(origin, environ)
    blob = _client_to_blob(origin, now, client)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(blob, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _cookie_header(auth_token: str, ct0: str) -> str:
    return f"auth_token={auth_token}; ct0={ct0}"


def _asset_origin(origin: str) -> str:
    if origin.rstrip("/") == DEFAULT_ORIGIN:
        return ASSET_ORIGIN
    return origin.rstrip("/")


def _rewrite_asset_url(url: str, origin: str) -> str:
    if origin.rstrip("/") == DEFAULT_ORIGIN:
        return url
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc in {
        "abs.twimg.com",
        "x.com",
        "twitter.com",
    }:
        return join_url(origin, parsed.path)
    if url.startswith("/"):
        return join_url(origin, url)
    return url


def _page_headers(auth_token: str, ct0: str) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": _cookie_header(auth_token, ct0),
        "User-Agent": BROWSER_UA,
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
    }


def _graphql_headers(
    auth_token: str,
    ct0: str,
    tid: str,
    *,
    origin: str,
    referer_path: str = "/search",
) -> dict[str, str]:
    referer = join_url(origin, referer_path)
    return {
        "Accept": "*/*",
        "Authorization": f"Bearer {WEB_BEARER}",
        "Content-Type": "application/json",
        "Cookie": _cookie_header(auth_token, ct0),
        "Referer": referer,
        "User-Agent": BROWSER_UA,
        "x-client-transaction-id": tid,
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
    }


def _execute_text(
    request: HttpRequest,
    *,
    transport: Transport | None,
    timeout: float,
) -> str:
    send = transport if transport is not None else (
        lambda req: urllib_transport(req, timeout=timeout)
    )
    try:
        response = send(request)
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderHttpError("x", 0, str(exc)) from exc
    text = response.body.decode("utf-8", errors="replace")
    if response.status in {401, 403}:
        raise MissingKeyError(
            "x", ("X_AUTH_TOKEN", "X_CT0"), detail=COOKIE_EXPIRED
        )
    if response.status >= 400:
        raise ProviderHttpError("x", response.status, text[:500] or "empty body")
    if not text.strip():
        raise ProviderHttpError("x", response.status, "empty response body")
    return text


def _raise_if_expired(exc: ProviderHttpError) -> None:
    if exc.status in {401, 403}:
        raise MissingKeyError(
            "x", ("X_AUTH_TOKEN", "X_CT0"), detail=COOKIE_EXPIRED
        ) from exc


def _graphql_json(
    request: HttpRequest,
    *,
    transport: Transport | None,
    timeout: float,
) -> Any:
    try:
        return execute_json(
            request, provider="x", transport=transport, timeout=timeout
        )
    except ProviderHttpError as exc:
        _raise_if_expired(exc)
        raise


def build_home_request(
    *,
    auth_token: str,
    ct0: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=join_url(origin, HOME_PATH),
        headers=_page_headers(auth_token, ct0),
        body=None,
    )


def build_asset_request(url: str, *, auth_token: str, ct0: str) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=url,
        headers={
            "Accept": "*/*",
            "Cookie": _cookie_header(auth_token, ct0),
            "User-Agent": BROWSER_UA,
            "Referer": "https://x.com/",
        },
        body=None,
    )


def parse_graphql_ops(js: str) -> dict[str, GraphQLOp]:
    ops: dict[str, GraphQLOp] = {}
    for match in _OP_RE.finditer(js):
        query_id, name, flags_js = match.group(1), match.group(2), match.group(3)
        flags = re.findall(r'"([^"]+)"', flags_js)
        if not flags:
            flags = re.findall(r"'([^']+)'", flags_js)
        features = {flag: DEFAULT_FEATURES.get(flag, True) for flag in flags}
        ops[name] = GraphQLOp(query_id=query_id, features=features)
    return ops


def _features_for(op: GraphQLOp | None) -> dict[str, bool]:
    if op is not None and op.features:
        return op.features
    return dict(DEFAULT_FEATURES)


def _query_id(ops: dict[str, GraphQLOp], name: str) -> str:
    if name in ops and ops[name].query_id:
        return ops[name].query_id
    fallback = FALLBACK_QUERY_IDS.get(name)
    if fallback:
        return fallback
    raise ProviderHttpError("x", 0, f"missing GraphQL query id for {name}")


def _network_bootstrap(
    *,
    auth_token: str,
    ct0: str,
    origin: str,
    transport: Transport | None,
    timeout: float,
) -> XClient:
    home = _execute_text(
        build_home_request(auth_token=auth_token, ct0=ct0, origin=origin),
        transport=transport,
        timeout=timeout,
    )
    asset = _asset_origin(origin)
    ondemand = _execute_text(
        build_asset_request(
            _rewrite_asset_url(ondemand_url(extract_ondemand_hash(home), asset), origin),
            auth_token=auth_token,
            ct0=ct0,
        ),
        transport=transport,
        timeout=timeout,
    )
    tx = ClientTransaction.from_documents(home, ondemand)
    ops: dict[str, GraphQLOp] = {}
    main_src = extract_main_script_url(home)
    if main_src:
        if main_src.startswith("/"):
            main_src = join_url(asset, main_src)
        main_js = _execute_text(
            build_asset_request(
                _rewrite_asset_url(main_src, origin),
                auth_token=auth_token,
                ct0=ct0,
            ),
            transport=transport,
            timeout=timeout,
        )
        ops = parse_graphql_ops(main_js)
    return XClient(tx=tx, ops=ops)


def bootstrap(
    *,
    auth_token: str,
    ct0: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    clock: Callable[[], float] | None = None,
    cache: dict[str, tuple[float, XClient]] | None = None,
    environ: Mapping[str, str] | None = None,
) -> XClient:
    now = (clock or time.time)()
    key = origin.rstrip("/")
    env = os.environ if environ is None else environ
    if cache is not None:
        hit = cache.get(key)
        if hit is not None and now - hit[0] < BOOTSTRAP_TTL_S:
            return hit[1]
        client = _network_bootstrap(
            auth_token=auth_token,
            ct0=ct0,
            origin=origin,
            transport=transport,
            timeout=timeout,
        )
        cache[key] = (now, client)
        return client
    if transport is None:
        disk = _read_disk_bootstrap(key, env, now)
        if disk is not None:
            return disk
    client = _network_bootstrap(
        auth_token=auth_token,
        ct0=ct0,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    if transport is None:
        _write_disk_bootstrap(key, env, now, client)
    return client


def _product_name(product: str) -> str:
    key = (product or "latest").strip().lower()
    if key not in PRODUCTS:
        raise ProviderHttpError(
            "x", 0, f"unknown product {product!r}; use latest, top, people, media"
        )
    return PRODUCTS[key]


def build_search_request(
    query: str,
    *,
    auth_token: str,
    ct0: str,
    query_id: str,
    tid: str,
    count: int = 20,
    product: str = "Latest",
    cursor: str | None = None,
    features: dict[str, bool] | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    variables: dict[str, Any] = {
        "rawQuery": query,
        "count": count,
        "querySource": "typed_query",
        "product": product,
        "withGrokTranslatedBio": False,
        "withQuickPromoteEligibilityTweetFields": False,
    }
    if cursor:
        variables["cursor"] = cursor
    url = with_query(
        join_url(origin, f"/i/api/graphql/{query_id}/SearchTimeline"),
        {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(
                features or DEFAULT_FEATURES, separators=(",", ":")
            ),
        },
    )
    return HttpRequest(
        method="GET",
        url=url,
        headers=_graphql_headers(auth_token, ct0, tid, origin=origin),
        body=None,
    )


def build_thread_request(
    tweet_id: str,
    *,
    auth_token: str,
    ct0: str,
    query_id: str,
    tid: str,
    cursor: str | None = None,
    features: dict[str, bool] | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    variables: dict[str, Any] = {
        "focalTweetId": tweet_id,
        "referrer": "tweet",
        "with_rux_injections": False,
        "rankingMode": "Relevance",
        "includePromotedContent": True,
        "withCommunity": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withBirdwatchNotes": True,
        "withVoice": True,
        "withV2Timeline": True,
    }
    if cursor:
        variables["cursor"] = cursor
    url = with_query(
        join_url(origin, f"/i/api/graphql/{query_id}/TweetDetail"),
        {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(
                features or DEFAULT_FEATURES, separators=(",", ":")
            ),
            "fieldToggles": json.dumps(TWEET_FIELD_TOGGLES, separators=(",", ":")),
        },
    )
    return HttpRequest(
        method="GET",
        url=url,
        headers=_graphql_headers(
            auth_token,
            ct0,
            tid,
            origin=origin,
            referer_path=f"/i/web/status/{tweet_id}",
        ),
        body=None,
    )


def parse_tweet_ref(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ProviderHttpError("x", 0, "missing tweet id or URL")
    if raw.isdigit():
        return raw
    path = raw
    if "://" in raw:
        path = urlparse(raw).path or raw
    match = _STATUS_RE.search(path)
    if match:
        return match.group(1)
    if path.strip("/").isdigit():
        return path.strip("/")
    raise ProviderHttpError("x", 0, f"invalid tweet id or URL: {value}")


def _user_core(result: dict[str, Any]) -> dict[str, Any]:
    user = ((result.get("core") or {}).get("user_results") or {}).get("result")
    if not isinstance(user, dict):
        return {}
    core = user.get("core") if isinstance(user.get("core"), dict) else {}
    legacy = user.get("legacy") if isinstance(user.get("legacy"), dict) else {}
    return {
        "id": user.get("rest_id"),
        "name": core.get("name") or legacy.get("name"),
        "username": core.get("screen_name") or legacy.get("screen_name"),
    }


def _tweet_text(result: dict[str, Any], legacy: dict[str, Any]) -> str | None:
    note = result.get("note_tweet")
    if isinstance(note, dict):
        nested = (note.get("note_tweet_results") or {}).get("result")
        if isinstance(nested, dict) and isinstance(nested.get("text"), str):
            return nested["text"]
    text = legacy.get("full_text") or legacy.get("text")
    return text if isinstance(text, str) else None


def _expanded_urls(legacy: dict[str, Any]) -> list[dict[str, Any]]:
    entities = legacy.get("entities")
    if not isinstance(entities, dict):
        return []
    raw = entities.get("urls")
    if not isinstance(raw, list):
        return []
    urls: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tco = item.get("url")
        expanded = item.get("expanded_url") or item.get("unwound_url")
        if not tco and not expanded:
            continue
        urls.append(
            {
                "url": tco,
                "expanded_url": expanded,
                "display_url": item.get("display_url"),
            }
        )
    return urls


def _best_video_url(media: dict[str, Any]) -> str | None:
    info = media.get("video_info")
    if not isinstance(info, dict):
        return None
    variants = info.get("variants")
    if not isinstance(variants, list):
        return None
    best: str | None = None
    best_br = -1
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        href = variant.get("url")
        if not isinstance(href, str) or not href:
            continue
        ctype = str(variant.get("content_type") or "")
        if "mp4" not in ctype and not href.endswith(".mp4"):
            continue
        try:
            bitrate = int(variant.get("bitrate") or 0)
        except (TypeError, ValueError):
            bitrate = 0
        if bitrate >= best_br:
            best_br = bitrate
            best = href
    return best


def _media_items(tweet: dict[str, Any], legacy: dict[str, Any]) -> list[dict[str, Any]]:
    bags: list[Any] = [legacy.get("extended_entities"), legacy.get("entities")]
    if tweet is not legacy:
        bags.extend(
            [
                (tweet.get("legacy") or {}).get("extended_entities")
                if isinstance(tweet.get("legacy"), dict)
                else None,
                tweet.get("extended_entities"),
            ]
        )
    source: list[Any] | None = None
    for bag in bags:
        if isinstance(bag, dict) and isinstance(bag.get("media"), list):
            source = bag["media"]
            break
    if not source:
        return []
    items: list[dict[str, Any]] = []
    for media in source:
        if not isinstance(media, dict):
            continue
        href = media.get("media_url_https") or media.get("media_url")
        kind = media.get("type")
        alt = media.get("ext_alt_text") or media.get("alt_text")
        video = _best_video_url(media)
        if not href and not video:
            continue
        record: dict[str, Any] = {"type": kind, "url": href, "alt": alt}
        if video:
            record["video_url"] = video
        items.append(record)
    return items


def _view_count(tweet: dict[str, Any]) -> int | None:
    views = tweet.get("views")
    if not isinstance(views, dict):
        return None
    count = views.get("count")
    if count is None:
        return None
    try:
        return int(count)
    except (TypeError, ValueError):
        return None


def _in_reply_to(legacy: dict[str, Any]) -> dict[str, Any] | None:
    status_id = legacy.get("in_reply_to_status_id_str")
    username = legacy.get("in_reply_to_screen_name")
    if not status_id and not username:
        return None
    return {"id": status_id, "username": username}


def _retweet_source(tweet: dict[str, Any], legacy: dict[str, Any]) -> Any:
    for bag in (tweet, legacy):
        if not isinstance(bag, dict):
            continue
        wrapped = bag.get("retweeted_status_result")
        if isinstance(wrapped, dict) and "result" in wrapped:
            return wrapped.get("result")
        nested = bag.get("retweeted_status")
        if isinstance(nested, dict):
            return nested
    return None


def _unwrap_tweet(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    typename = result.get("__typename")
    if typename == "TweetWithVisibilityResults":
        return _unwrap_tweet(result.get("tweet"))
    if typename in {"TweetUnavailable", "User", "UserUnavailable"}:
        return None
    if typename == "Tweet":
        return result
    legacy = result.get("legacy")
    if isinstance(legacy, dict) and (legacy.get("full_text") or legacy.get("id_str")):
        return result
    return None


def _tweet_record(result: Any) -> dict[str, Any] | None:
    tweet = _unwrap_tweet(result)
    if tweet is None:
        return None
    legacy = tweet.get("legacy") if isinstance(tweet.get("legacy"), dict) else {}
    rest_id = tweet.get("rest_id") or legacy.get("id_str")
    if not isinstance(rest_id, str) or not rest_id:
        return None
    user = _user_core(tweet)
    username = user.get("username")
    url = f"https://x.com/{username}/status/{rest_id}" if username else (
        f"https://x.com/i/web/status/{rest_id}"
    )
    record: dict[str, Any] = {
        "type": "tweet",
        "id": rest_id,
        "url": url,
        "text": _tweet_text(tweet, legacy),
        "created_at": legacy.get("created_at"),
        "lang": legacy.get("lang"),
        "likes": legacy.get("favorite_count"),
        "reposts": legacy.get("retweet_count"),
        "replies": legacy.get("reply_count"),
        "quotes": legacy.get("quote_count"),
        "bookmarks": legacy.get("bookmark_count"),
        "user": user or None,
    }
    urls = _expanded_urls(legacy)
    if urls:
        record["urls"] = urls
    media = _media_items(tweet, legacy)
    if media:
        record["media"] = media
    views = _view_count(tweet)
    if views is not None:
        record["views"] = views
    reply = _in_reply_to(legacy)
    if reply:
        record["in_reply_to"] = reply
    retweeted = _retweet_source(tweet, legacy)
    if retweeted is not None:
        nested_rt = _tweet_record(retweeted)
        if nested_rt:
            record["retweet"] = nested_rt
    quoted = tweet.get("quoted_status_result")
    if isinstance(quoted, dict):
        nested = _tweet_record(quoted.get("result"))
        if nested:
            record["quoted"] = nested
    return record


def _user_record(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if result.get("__typename") in {"UserUnavailable"}:
        return None
    core = result.get("core") if isinstance(result.get("core"), dict) else {}
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    username = core.get("screen_name") or legacy.get("screen_name")
    rest_id = result.get("rest_id") or legacy.get("id_str")
    if not isinstance(username, str) or not username:
        return None
    bio = None
    profile_bio = result.get("profile_bio")
    if isinstance(profile_bio, dict) and isinstance(profile_bio.get("description"), str):
        bio = profile_bio["description"]
    elif isinstance(legacy.get("description"), str):
        bio = legacy["description"]
    counts = result.get("relationship_counts")
    followers = counts.get("followers") if isinstance(counts, dict) else legacy.get(
        "followers_count"
    )
    return {
        "type": "user",
        "id": rest_id,
        "url": f"https://x.com/{username}",
        "name": core.get("name") or legacy.get("name"),
        "username": username,
        "bio": bio,
        "followers": followers,
        "verified": bool(result.get("is_blue_verified") or legacy.get("verified")),
    }


def _walk_entries(node: Any, tweets: list[dict[str, Any]], cursors: dict[str, str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_entries(item, tweets, cursors)
        return
    if not isinstance(node, dict):
        return
    cursor_type = node.get("cursorType")
    if cursor_type and isinstance(node.get("value"), str):
        cursors[str(cursor_type)] = node["value"]
    tweet_results = node.get("tweet_results")
    if isinstance(tweet_results, dict) and "result" in tweet_results:
        record = _tweet_record(tweet_results.get("result"))
        if record and all(item.get("id") != record["id"] for item in tweets):
            tweets.append(record)
    if node.get("itemType") == "TimelineUser":
        record = _user_record((node.get("user_results") or {}).get("result"))
        if record and all(item.get("id") != record["id"] for item in tweets):
            tweets.append(record)
    for key, value in node.items():
        if key in {"tweet_results", "user_results"}:
            continue
        if isinstance(value, (dict, list)):
            _walk_entries(value, tweets, cursors)


def _timeline_root(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    search = (
        ((data.get("search_by_raw_query") or {}).get("search_timeline") or {}).get(
            "timeline"
        )
    )
    if search:
        return search
    detail = data.get("threaded_conversation_with_injections_v2")
    if isinstance(detail, dict):
        return detail.get("timeline") or detail
    return data


def parse_timeline(payload: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    tweets: list[dict[str, Any]] = []
    cursors: dict[str, str] = {}
    _walk_entries(_timeline_root(payload), tweets, cursors)
    return tweets, cursors


def _project_record(record: Any, fields: list[str]) -> Any:
    if not isinstance(record, dict) or not fields:
        return record
    keep = set(fields)
    out = {key: value for key, value in record.items() if key in keep}
    for nested in ("quoted", "retweet"):
        if nested in out:
            out[nested] = _project_record(out[nested], fields)
    return out


def project_payload(payload: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return payload
    names = [item.strip() for item in fields if item and item.strip()]
    if not names:
        return payload
    out = dict(payload)
    if isinstance(out.get("results"), list):
        out["results"] = [_project_record(item, names) for item in out["results"]]
    if isinstance(out.get("tweet"), dict):
        out["tweet"] = _project_record(out["tweet"], names)
    if isinstance(out.get("replies"), list):
        out["replies"] = [_project_record(item, names) for item in out["replies"]]
    return out


def parse_search_response(payload: Any) -> dict[str, Any]:
    tweets, cursors = parse_timeline(payload)
    return {
        "provider": "x",
        "operation": "search",
        "results": tweets,
        "cursor": cursors.get("Bottom") or cursors.get("ShowMore"),
        "cursors": cursors or None,
    }


def parse_thread_response(payload: Any, tweet_id: str) -> dict[str, Any]:
    tweets, cursors = parse_timeline(payload)
    focal = next((item for item in tweets if item.get("id") == tweet_id), None)
    replies = [item for item in tweets if item.get("id") != tweet_id]
    return {
        "provider": "x",
        "operation": "thread",
        "id": tweet_id,
        "url": (focal or {}).get("url") or f"https://x.com/i/web/status/{tweet_id}",
        "tweet": focal,
        "replies": replies,
        "cursor": cursors.get("Bottom") or cursors.get("ShowMore"),
        "cursors": cursors or None,
    }


def search(
    query: str,
    *,
    auth_token: str,
    ct0: str,
    count: int = 20,
    product: str = "latest",
    cursor: str | None = None,
    fields: list[str] | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    client: XClient | None = None,
    clock: Callable[[], float] | None = None,
    cache: dict[str, tuple[float, XClient]] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    needle = (query or "").strip()
    if not needle:
        raise ProviderHttpError("x", 0, "missing search query")
    session = client or bootstrap(
        auth_token=auth_token,
        ct0=ct0,
        origin=origin,
        transport=transport,
        timeout=timeout,
        clock=clock,
        cache=cache,
        environ=environ,
    )
    op_name = "SearchTimeline"
    query_id = _query_id(session.ops, op_name)
    path = f"/i/api/graphql/{query_id}/SearchTimeline"
    tid = session.tx.generate_transaction_id("GET", path)
    request = build_search_request(
        needle,
        auth_token=auth_token,
        ct0=ct0,
        query_id=query_id,
        tid=tid,
        count=count,
        product=_product_name(product),
        cursor=cursor,
        features=_features_for(session.ops.get(op_name)),
        origin=origin,
    )
    payload = _graphql_json(request, transport=transport, timeout=timeout)
    out = parse_search_response(payload)
    out["query"] = needle
    out["product"] = _product_name(product)
    return project_payload(out, fields)


def thread(
    target: str,
    *,
    auth_token: str,
    ct0: str,
    cursor: str | None = None,
    fields: list[str] | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    client: XClient | None = None,
    clock: Callable[[], float] | None = None,
    cache: dict[str, tuple[float, XClient]] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    tweet_id = parse_tweet_ref(target)
    session = client or bootstrap(
        auth_token=auth_token,
        ct0=ct0,
        origin=origin,
        transport=transport,
        timeout=timeout,
        clock=clock,
        cache=cache,
        environ=environ,
    )
    op_name = "TweetDetail"
    query_id = _query_id(session.ops, op_name)
    path = f"/i/api/graphql/{query_id}/TweetDetail"
    tid = session.tx.generate_transaction_id("GET", path)
    request = build_thread_request(
        tweet_id,
        auth_token=auth_token,
        ct0=ct0,
        query_id=query_id,
        tid=tid,
        cursor=cursor,
        features=_features_for(session.ops.get(op_name)),
        origin=origin,
    )
    payload = _graphql_json(request, transport=transport, timeout=timeout)
    return project_payload(parse_thread_response(payload, tweet_id), fields)
