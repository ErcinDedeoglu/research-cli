"""TGStat Premium-search website (HTTP). Public Telegram post index.

Not the paid Search API. Needs logged-in site cookies (`TGSTAT_IDR` /
`TGSTAT_SIRK`, optional `TGSTAT_CSRK` / `TGSTAT_SETTINGS`) from
tgstat.com — same idea as X cookies. Search POSTs `/search/list` (20
hits per page, hard ceiling 1000). Mentions chart, xlsx export, and
source list use the same form. CLI command is `research-cli telegram search` (errors still name tgstat).
Files are t.me links; download is `research-cli telegram download`.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import unquote, urlencode

from research_cli.errors import ProviderHttpError
from research_cli.http import (
    HttpRequest,
    Transport,
    join_url,
    urllib_transport,
)

DEFAULT_ORIGIN = "https://tgstat.com"
SEARCH_PATH = "/search"
LIST_PATH = "/search/list"
MENTIONS_PATH = "/search/mentions-chart"
EXPORT_PATH = "/search/export/xls"
PEER_TYPES = ("all", "channel", "chat")
SORTS = ("date", "views")
SOURCE_SORTS = ("members", "freq")
FORWARDS = ("all", "hide", "only")
CHART_GROUPS = ("day", "month")
VIEWS_RANGES = ("all", "lt1000", "1k-10k", "10k")
_VIEWS_RANGE_VALUES = {
    "all": "all",
    "lt1000": "0",
    "1k-10k": "1",
    "10k": "2",
}
PAGE_SIZE = 20
MAX_POSTS = 1000
MIN_INVITE_HASH = 8
FILE_MEDIA_TYPES = ("document", "photo", "video")
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DOWNLOAD_JOBS = 4
GetMessage = Callable[[str], dict[str, Any]]
TelegramDownload = Callable[[str, str | None], dict[str, Any]]
GetMany = Callable[..., list[dict[str, Any]]]
DownloadMany = Callable[..., list[dict[str, Any]]]
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)

COUNTRIES = {
    "global": "Without a specific territory",
    "ru": "Russia",
    "ua": "Ukraine",
    "uz": "Uzbekistan",
    "by": "Belarus",
    "kz": "Kazakhstan",
    "kg": "Kyrgyzstan",
    "ir": "Iran",
    "in": "India",
    "cn": "China",
    "et": "Ethiopia",
    "ab": "Abkhazia",
    "au": "Australia",
    "at": "Austria",
    "az": "Azerbaijan",
    "al": "Albania",
    "dz": "Algeria",
    "ar": "Argentina",
    "am": "Armenia",
    "bd": "Bangladesh",
    "be": "Belgium",
    "bg": "Bulgaria",
    "ba": "Bosnia and Herzegovina",
    "br": "Brazil",
    "gb": "United Kingdom",
    "hu": "Hungary",
    "ve": "Venezuela",
    "vn": "Vietnam",
    "de": "Germany",
    "gr": "Greece",
    "ge": "Georgia",
    "dk": "Denmark",
    "eg": "Egypt",
    "il": "Israel",
    "id": "Indonesia",
    "iq": "Iraq",
    "ie": "Ireland",
    "es": "Spain",
    "it": "Italy",
    "ye": "Yemen",
    "kh": "Cambodia",
    "ca": "Canada",
    "cy": "Cyprus",
    "kr": "Korea",
    "cu": "Cuba",
    "lv": "Latvia",
    "lt": "Lithuania",
    "mk": "North Macedonia",
    "my": "Malaysia",
    "mx": "Mexico",
    "md": "Moldova",
    "mn": "Mongolia",
    "mm": "Myanmar",
    "ng": "Nigeria",
    "nl": "Netherlands",
    "no": "Norway",
    "ae": "UAE",
    "pk": "Pakistan",
    "pa": "Panama",
    "pl": "Poland",
    "pt": "Portugal",
    "ro": "Romania",
    "sa": "Saudi Arabia",
    "rs": "Serbia",
    "sg": "Singapore",
    "sy": "Syria",
    "sk": "Slovakia",
    "si": "Slovenia",
    "so": "Somalia",
    "sd": "Sudan",
    "us": "USA",
    "tj": "Tajikistan",
    "th": "Thailand",
    "tz": "Tanzania",
    "tm": "Turkmenistan",
    "tr": "Turkey",
    "uy": "Uruguay",
    "ph": "Philippines",
    "fi": "Finland",
    "fr": "France",
    "hr": "Croatia",
    "me": "Montenegro",
    "cz": "Czech Republic",
    "ch": "Switzerland",
    "se": "Sweden",
    "lk": "Sri Lanka",
    "ec": "Ecuador",
    "ee": "Estonia",
    "za": "South Africa",
    "jp": "Japan",
}
LANGUAGES = {
    "russian": "Russian",
    "english": "English",
    "uzbek": "Uzbek",
    "ukrainian": "Ukrainian",
    "kazakh": "Kazakh",
    "belarus": "Belarusian",
    "farsi": "Persian",
    "hindi": "Hindi",
    "chinese": "Chinese",
    "tamil": "Tamil",
    "amhar": "Amharic",
}
CATEGORIES = {
    "telegram": "Telegram",
    "business": "Business and startups",
    "blogs": "Blogs",
    "gambling": "Bookmaking",
    "video": "Video and films",
    "darknet": "Darknet",
    "design": "Design",
    "adult": "Adult",
    "other": "Other",
    "food": "Food and cooking",
    "health": "Health and Fitness",
    "games": "Games",
    "instagram": "Instagram",
    "construction": "Interior and construction",
    "art": "Art",
    "pics": "Pictures and photos",
    "career": "Career",
    "books": "Books",
    "crypto": "Cryptocurrencies",
    "courses": "Courses and guides",
    "language": "Linguistics",
    "marketing": "Marketing, PR, advertising",
    "medicine": "Medicine",
    "beauty": "Fashion and beauty",
    "music": "Music",
    "news": "News and media",
    "education": "Education",
    "edutainment": "Edutainment",
    "politics": "Politics",
    "law": "Law",
    "nature": "Nature",
    "sales": "Sales",
    "psychology": "Psychology",
    "travels": "Travel",
    "religion": "Religion",
    "handmade": "Handiwork",
    "babies": "Family & Children",
    "apps": "Software & Applications",
    "sport": "Sport",
    "tech": "Technologies",
    "transport": "Transport",
    "quotes": "Quotes",
    "shock": "Shock content",
    "esoterics": "Esoterics",
    "economics": "Economics",
    "erotica": "Erotic",
    "entertainment": "Humor and entertainment",
}

_CSRF_RE = re.compile(
    r'name=["\']_tgstat_csrk["\'][^>]*value=["\']([^"\']+)["\']'
    r'|value=["\']([^"\']+)["\'][^>]*name=["\']_tgstat_csrk["\']',
    re.I,
)
_POST_TEXT_RE = re.compile(
    r'class="[^"]*post-text[^"]*"[^>]*>(.*?)</div>', re.I | re.S
)
_TME_RE = re.compile(
    r"https?://(?:ttttt\.me|t\.me|telegram\.me)/"
    r"(?!joinchat(?:/|$)|c/)([A-Za-z0-9_]+)/(\d+)",
    re.I,
)
_JOIN_RE = re.compile(
    r"https?://(?:ttttt\.me|t\.me|telegram\.me)/"
    rf"(?:joinchat/|\+)([\w-]{{{MIN_INVITE_HASH},}})(?:/(\d+))?",
    re.I,
)
_REL_MSG_RE = re.compile(
    r'(?:https?://(?:www\.)?tgstat\.[^"/]+)?/(?:[a-z]{2}/)?(?:channel|chat)/@([A-Za-z0-9_]+)/(\d+)',
    re.I,
)
_CHANNEL_RE = re.compile(r'(?:tgstat\.[^/]+/[^"]*)?/@([A-Za-z0-9_]+)', re.I)
_SMALL_RE = re.compile(r"<small>(.*?)</small>", re.I | re.S)
_TITLE_RE = re.compile(r"<h5[^>]*>\s*<a[^>]*>(.*?)</a>", re.I | re.S)
_ICON_COUNT_RE = re.compile(
    r'<i class="(uil-eye|uil-share-alt|uil-corner-up-right)"></i>\s*(\d+)',
    re.I,
)
_FORWARD_FROM_RE = re.compile(
    r"Forward from:\s*<a[^>]*>\s*(.*?)\s*</a>", re.I | re.S
)
_IMG_RE = re.compile(r'class="post-img-img"[^>]*src=["\']([^"\']+)["\']', re.I)
_SOURCE_OPEN_RE = re.compile(
    r'<div[^>]*class="[^"]*channel-source-item[^"]*"[^>]*>', re.I
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.I)


def cookie_header(
    idr: str,
    sirk: str,
    *,
    csrf: str = "",
    settings: str = "",
) -> str:
    parts = [f"tgstat_idrk={idr}", f"tgstat_sirk={sirk}"]
    if csrf:
        parts.append(f"_tgstat_csrk={csrf}")
    if settings:
        parts.append(f"tgstat_settings={settings}")
    return "; ".join(parts)


def _headers(cookie: str, *, ajax: bool = False, origin: str = DEFAULT_ORIGIN) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/html, */*" if ajax else "text/html, */*",
        "User-Agent": BROWSER_UA,
        "Cookie": cookie,
        "Origin": origin.rstrip("/"),
        "Referer": join_url(origin, SEARCH_PATH),
    }
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    return headers


def _dot_date(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw):
        return raw
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        year, month, day = raw.split("-")
        return f"{day}.{month}.{year}"
    if raw.isdigit():
        stamp = datetime.fromtimestamp(int(raw), tz=timezone.utc)
        return stamp.strftime("%d.%m.%Y")
    raise ProviderHttpError(
        "tgstat", 0, "dates must be YYYY-MM-DD, DD.MM.YYYY, or unix seconds"
    )


def _https_tme(link: str | None) -> str | None:
    raw = (link or "").strip()
    if not raw:
        return None
    raw = raw.replace("https://ttttt.me/", "https://t.me/").replace(
        "http://ttttt.me/", "https://t.me/"
    )
    if raw.startswith("//"):
        raw = "https:" + raw
    if raw.startswith("t.me/") or raw.startswith("telegram.me/"):
        return "https://" + raw
    return raw


def _invite_hash_ok(value: str | None) -> bool:
    raw = (value or "").strip()
    return len(raw) >= MIN_INVITE_HASH and bool(re.fullmatch(r"[\w-]+", raw))


def canonical_telegram_url(target: str) -> str | None:
    """Normalize a tgstat hit into a URL telegram download accepts."""
    raw = _https_tme(target) or (target or "").strip()
    join = _JOIN_RE.search(raw)
    if join and _invite_hash_ok(join.group(1)):
        url = f"https://t.me/joinchat/{join.group(1)}"
        if join.group(2):
            url += f"/{join.group(2)}"
        return url
    tme = _TME_RE.search(raw)
    if tme and tme.group(1).lower() not in {"joinchat", "c"}:
        return f"https://t.me/{tme.group(1)}/{tme.group(2)}"
    internal = re.search(
        r"(?:t\.me|telegram\.me|ttttt\.me)/c/(\d+)/(\d+)", raw, re.I
    )
    if internal:
        return f"https://t.me/c/{internal.group(1)}/{internal.group(2)}"
    return None


def _attach_telegram(record: dict[str, Any]) -> dict[str, Any]:
    invite = record.get("invite")
    if invite and not _invite_hash_ok(str(invite)):
        record.pop("invite", None)
        invite = None
        if str(record.get("username") or "").lower() in {"joinchat", "c"}:
            record.pop("username", None)
            record.pop("url", None)
            record.pop("link", None)
            record.pop("message_id", None)
    if invite and record.get("message_id"):
        url = f"https://t.me/joinchat/{invite}/{record['message_id']}"
        record["url"] = url
        record["link"] = url
        record["private"] = True
    elif record.get("url"):
        url = canonical_telegram_url(str(record["url"]))
        if url:
            record["url"] = url
            record["link"] = url
        else:
            record.pop("url", None)
            record.pop("link", None)
    if record.get("username") and record.get("message_id") and not record.get("url"):
        url = f"https://t.me/{record['username']}/{record['message_id']}"
        record["url"] = url
        record["link"] = url
    has_media = bool(record.get("media") or record.get("image"))
    record["has_media"] = has_media
    if invite:
        record["private"] = True
    target = record.get("url")
    if target:
        record["telegram"] = {
            "target": target,
            "has_media": has_media,
            "private": bool(invite),
        }
    return record


def _plain(html: str) -> str:
    text = unescape(_TAG_RE.sub(" ", html.replace("<br>", "\n").replace("<br/>", "\n")))
    return _WS_RE.sub(" ", text).strip()


def _execute(
    request: HttpRequest,
    *,
    transport: Transport | None,
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    send = transport if transport is not None else (
        lambda req: urllib_transport(req, timeout=timeout)
    )
    try:
        response = send(request)
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderHttpError("tgstat", 0, str(exc)) from exc
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    return response.status, headers, response.body


def extract_csrf(html: str) -> str:
    match = _CSRF_RE.search(html or "")
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").strip()


def parse_post_html(chunk: str) -> dict[str, Any] | None:
    ident_match = re.search(r'id="post-(\d+)"', chunk, re.I)
    tme = _TME_RE.search(chunk)
    text_match = _POST_TEXT_RE.search(chunk)
    if not ident_match and not tme and not text_match:
        return None
    record: dict[str, Any] = {}
    if ident_match:
        record["id"] = int(ident_match.group(1))
    if tme and tme.group(1).lower() not in {"joinchat", "c"}:
        url = f"https://t.me/{tme.group(1)}/{tme.group(2)}"
        record["url"] = url
        record["link"] = url
        record["username"] = tme.group(1)
        record["message_id"] = int(tme.group(2))
    else:
        join = _JOIN_RE.search(chunk)
        if join and _invite_hash_ok(join.group(1)):
            record["invite"] = join.group(1)
            url = f"https://t.me/joinchat/{join.group(1)}"
            record["url"] = url
            record["link"] = url
            if join.group(2):
                record["message_id"] = int(join.group(2))
        else:
            rel = _REL_MSG_RE.search(chunk)
            if rel:
                url = f"https://t.me/{rel.group(1)}/{rel.group(2)}"
                record["url"] = url
                record["link"] = url
                record["username"] = rel.group(1)
                record["message_id"] = int(rel.group(2))
    if re.search(r'post-container[^"]*\bdeleted\b', chunk, re.I):
        record["deleted"] = True
    if re.search(r"\bisForwarded\b", chunk):
        record["forwarded"] = True
    forwarded = _FORWARD_FROM_RE.search(chunk)
    if forwarded:
        record["forwarded"] = True
        name = _plain(forwarded.group(1))
        if name:
            record["forwarded_from"] = name
    channel = _CHANNEL_RE.search(chunk)
    if channel and "username" not in record:
        record["username"] = channel.group(1)
    title = _TITLE_RE.search(chunk)
    if title:
        name = _plain(title.group(1))
        if name:
            record["title"] = name
    if text_match:
        text = _plain(text_match.group(1))
        if text:
            record["text"] = text
    small = _SMALL_RE.search(chunk)
    if small:
        published = _plain(small.group(1))
        if published:
            record["published"] = published
    for icon, raw in _ICON_COUNT_RE.findall(chunk):
        kind = icon.lower()
        count = int(raw)
        if kind == "uil-eye":
            record["views"] = count
        elif kind == "uil-share-alt":
            record["quotes"] = count
        elif kind == "uil-corner-up-right":
            record["shares"] = count
    body_class = re.search(r'class="([^"]*post-body[^"]*)"', chunk, re.I)
    if body_class:
        classes = body_class.group(1)
        if "isPhoto" in classes:
            record["media"] = "photo"
        elif "isVideo" in classes:
            record["media"] = "video"
        elif "isDocument" in classes:
            record["media"] = "document"
        elif "isAudio" in classes:
            record["media"] = "audio"
    image = _IMG_RE.search(chunk)
    if image:
        record["image"] = image.group(1)
        record.setdefault("media", "photo")
    if not record:
        return None
    return _attach_telegram(record)


def parse_posts(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<div[^>]*id="post-\d+"[^>]*class="[^"]*post-container[\s\S]*?(?=<div[^>]*id="post-\d+"|$)',
        html or "",
        re.I,
    ):
        parsed = parse_post_html(match.group(0))
        if not parsed:
            continue
        key = str(parsed.get("url") or parsed.get("id"))
        if key in seen:
            continue
        seen.add(key)
        results.append(parsed)
    if results:
        return results
    parsed = parse_post_html(html or "")
    return [parsed] if parsed else []


def parse_sources(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _SOURCE_OPEN_RE.finditer(html or ""):
        tag = match.group(0)
        ident = re.search(r'data-id="(\d+)"', tag)
        if not ident:
            continue
        channel_id = ident.group(1)
        if channel_id in seen:
            continue
        seen.add(channel_id)
        freq = re.search(r'data-freq="(\d+)"', tag)
        members = re.search(r'data-members="(\d+)"', tag)
        chunk = (html or "")[match.start() : match.start() + 2000]
        title_match = re.search(
            r'class="[^"]*text-body[^"]*"[^>]*>(.*?)</div>', chunk, re.I | re.S
        )
        user = _CHANNEL_RE.search(chunk)
        record: dict[str, Any] = {"id": int(channel_id)}
        if freq:
            record["freq"] = int(freq.group(1))
        if members:
            record["members"] = int(members.group(1))
        if title_match:
            title = _plain(title_match.group(1))
            if title:
                record["title"] = title
        if user:
            record["username"] = user.group(1)
        results.append(record)
    return results


def _forwards_mode(forwards: str, hide_forwards: bool) -> str:
    mode = (forwards or "all").strip().lower()
    if mode == "all" and hide_forwards:
        return "hide"
    if mode not in FORWARDS:
        raise ProviderHttpError(
            "tgstat", 0, f"forwards must be one of {', '.join(FORWARDS)}"
        )
    return mode


def _views_value(views_range: str) -> str:
    key = (views_range or "all").strip().lower()
    if key in _VIEWS_RANGE_VALUES:
        return _VIEWS_RANGE_VALUES[key]
    if key in {"0", "1", "2", "all"}:
        return key
    raise ProviderHttpError(
        "tgstat", 0, f"views-range must be one of {', '.join(VIEWS_RANGES)}"
    )


def _search_fields(
    query: str,
    csrf: str,
    *,
    page: int = 0,
    offset: int = 0,
    peer_type: str = "all",
    start: str | None = None,
    end: str | None = None,
    hide_forwards: bool = False,
    hide_deleted: bool = False,
    strong: bool = False,
    extended: bool = False,
    only_mentioned: bool = False,
    minus_words: str | None = None,
    country: str | None = None,
    language: str | None = None,
    category: str | None = None,
    sort: str = "date",
    views_range: str = "all",
    channel_id: str | None = None,
    source_sort: str = "members",
    forwards: str = "all",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = (peer_type or "all").strip().lower()
    if kind not in PEER_TYPES:
        raise ProviderHttpError(
            "tgstat", 0, f"peer-type must be one of {', '.join(PEER_TYPES)}"
        )
    sort_key = (sort or "date").strip().lower()
    if sort_key not in SORTS:
        raise ProviderHttpError("tgstat", 0, f"sort must be one of {', '.join(SORTS)}")
    source_key = (source_sort or "members").strip().lower()
    if source_key not in SOURCE_SORTS:
        raise ProviderHttpError(
            "tgstat", 0, f"source-sort must be one of {', '.join(SOURCE_SORTS)}"
        )
    mode = _forwards_mode(forwards, hide_forwards)
    ident = re.sub(r"\D", "", str(channel_id or ""))
    fields: dict[str, Any] = {
        "_tgstat_csrk": csrf,
        "page": max(0, int(page)),
        "offset": max(0, int(offset)),
        "q": query,
        "peerType": kind,
        "startDate": _dot_date(start),
        "endDate": _dot_date(end),
        "strongSearch": "1" if strong else "0",
        "hideForwards": "1" if mode == "hide" else "0",
        "extendedSyntax": "1" if extended else "0",
        "hideDeleted": "1" if hide_deleted else "0",
        "onlyMentioned": "1" if only_mentioned else "0",
        "country": country or "",
        "language": language or "",
        "category": category or "",
        "minusWords": minus_words or "",
        "sort": sort_key,
        "facets[source_sort]": source_key,
        "facets[channel_id]": ident,
        "facets[views_range]": _views_value(views_range),
    }
    if mode == "only":
        fields["facets[is_forward][1]"] = "1"
    if extra:
        fields.update(extra)
    return fields


def _urlencoded(fields: dict[str, Any]) -> bytes:
    return urlencode(fields).encode("utf-8")


def build_search_page_request(
    *,
    cookie: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=join_url(origin, SEARCH_PATH),
        headers=_headers(cookie, origin=origin),
        body=None,
    )


def build_list_request(
    query: str,
    *,
    cookie: str,
    csrf: str,
    page: int,
    offset: int,
    peer_type: str = "all",
    start: str | None = None,
    end: str | None = None,
    hide_forwards: bool = False,
    hide_deleted: bool = False,
    strong: bool = False,
    extended: bool = False,
    only_mentioned: bool = False,
    minus_words: str | None = None,
    country: str | None = None,
    language: str | None = None,
    category: str | None = None,
    sort: str = "date",
    views_range: str = "all",
    channel_id: str | None = None,
    source_sort: str = "members",
    forwards: str = "all",
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    fields = _search_fields(
        query,
        csrf,
        page=page,
        offset=offset,
        peer_type=peer_type,
        start=start,
        end=end,
        hide_forwards=hide_forwards,
        hide_deleted=hide_deleted,
        strong=strong,
        extended=extended,
        only_mentioned=only_mentioned,
        minus_words=minus_words,
        country=country,
        language=language,
        category=category,
        sort=sort,
        views_range=views_range,
        channel_id=channel_id,
        source_sort=source_sort,
        forwards=forwards,
    )
    return HttpRequest(
        method="POST",
        url=join_url(origin, LIST_PATH),
        headers=_headers(cookie, ajax=True, origin=origin),
        body=_urlencoded(fields),
    )


def build_mentions_request(
    query: str,
    *,
    cookie: str,
    csrf: str,
    group: str = "day",
    origin: str = DEFAULT_ORIGIN,
    **filters: Any,
) -> HttpRequest:
    key = (group or "day").strip().lower()
    if key not in CHART_GROUPS:
        raise ProviderHttpError(
            "tgstat", 0, f"group must be one of {', '.join(CHART_GROUPS)}"
        )
    fields = _search_fields(query, csrf, extra={"group": key}, **filters)
    return HttpRequest(
        method="POST",
        url=join_url(origin, MENTIONS_PATH),
        headers=_headers(cookie, ajax=True, origin=origin),
        body=_urlencoded(fields),
    )


def build_export_request(
    query: str,
    *,
    cookie: str,
    csrf: str,
    origin: str = DEFAULT_ORIGIN,
    **filters: Any,
) -> HttpRequest:
    fields = _search_fields(query, csrf, **filters)
    headers = _headers(cookie, origin=origin)
    headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers["Accept"] = "*/*"
    return HttpRequest(
        method="POST",
        url=join_url(origin, EXPORT_PATH),
        headers=headers,
        body=_urlencoded(fields),
    )


def build_sources_request(
    query: str,
    *,
    cookie: str,
    csrf: str,
    origin: str = DEFAULT_ORIGIN,
    **filters: Any,
) -> HttpRequest:
    fields = _search_fields(query, csrf, **filters)
    headers = _headers(cookie, origin=origin)
    headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers=headers,
        body=_urlencoded(fields),
    )


def _load_csrf(
    cookie: str,
    *,
    origin: str,
    transport: Transport | None,
    timeout: float,
) -> str:
    status, _, body = _execute(
        build_search_page_request(cookie=cookie, origin=origin),
        transport=transport,
        timeout=timeout,
    )
    html = body.decode("utf-8", errors="replace")
    if status >= 400:
        raise ProviderHttpError("tgstat", status, html[:500])
    csrf = extract_csrf(html)
    if not csrf:
        raise ProviderHttpError(
            "tgstat",
            0,
            "tgstat session expired; recopy tgstat.com cookies "
            "(tgstat_idrk → TGSTAT_IDR, tgstat_sirk → TGSTAT_SIRK)",
        )
    return csrf


def me(
    *,
    cookie: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    _load_csrf(cookie, origin=origin, transport=transport, timeout=timeout)
    return {"provider": "tgstat", "operation": "me", "status": "ok"}


def _require_query(query: str) -> str:
    q = (query or "").strip()
    if not q:
        raise ProviderHttpError("tgstat", 0, "empty search query")
    return q


def _json_payload(status: int, body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace")
    if status >= 400:
        raise ProviderHttpError("tgstat", status, text[:500])
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderHttpError("tgstat", status, f"invalid JSON: {text[:300]}") from exc
    if not isinstance(payload, dict):
        raise ProviderHttpError("tgstat", status, "search failed")
    return payload


def search(
    query: str,
    *,
    cookie: str,
    limit: int = 20,
    offset: int = 0,
    peer_type: str = "all",
    start: str | None = None,
    end: str | None = None,
    hide_forwards: bool = False,
    hide_deleted: bool = False,
    strong: bool = False,
    extended: bool = False,
    only_mentioned: bool = False,
    minus_words: str | None = None,
    country: str | None = None,
    language: str | None = None,
    category: str | None = None,
    sort: str = "date",
    views_range: str = "all",
    channel_id: str | None = None,
    source_sort: str = "members",
    forwards: str = "all",
    include_private: bool = False,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    q = _require_query(query)
    filters = dict(
        peer_type=peer_type,
        start=start,
        end=end,
        hide_forwards=hide_forwards,
        hide_deleted=hide_deleted,
        strong=strong,
        extended=extended,
        only_mentioned=only_mentioned,
        minus_words=minus_words,
        country=country,
        language=language,
        category=category,
        sort=sort,
        views_range=views_range,
        channel_id=channel_id,
        source_sort=source_sort,
        forwards=forwards,
    )
    _search_fields(q, "x", **filters)
    want = max(1, min(int(limit), MAX_POSTS))
    start_offset = max(0, min(int(offset), MAX_POSTS - PAGE_SIZE))
    csrf = _load_csrf(cookie, origin=origin, transport=transport, timeout=timeout)
    results: list[dict[str, Any]] = []
    total: int | None = None
    page = start_offset // PAGE_SIZE
    cur = start_offset
    truncated = False
    while len(results) < want and cur <= MAX_POSTS - PAGE_SIZE:
        status, _, body = _execute(
            build_list_request(
                q,
                cookie=cookie,
                csrf=csrf,
                page=page,
                offset=cur,
                origin=origin,
                **filters,
            ),
            transport=transport,
            timeout=timeout,
        )
        if status >= 500:
            truncated = True
            break
        payload = _json_payload(status, body)
        if payload.get("status") != "ok":
            raise ProviderHttpError(
                "tgstat", status, str(payload.get("error") or "search failed")
            )
        batch = parse_posts(str(payload.get("html") or ""))
        if not batch:
            break
        results.extend(batch)
        if payload.get("totalCount") is not None:
            total = int(payload["totalCount"])
        next_offset = payload.get("nextOffset")
        has_more = bool(payload.get("hasMore"))
        if next_offset is None:
            cur += PAGE_SIZE
            page += 1
        else:
            cur = int(next_offset)
            page = int(payload.get("nextPage") or page + 1)
        if cur >= MAX_POSTS or not has_more:
            if cur >= MAX_POSTS:
                truncated = True
            break
    results = results[:want]
    if not include_private:
        results = [
            item
            for item in results
            if not (
                item.get("private")
                or (item.get("telegram") or {}).get("private")
            )
        ]
    out: dict[str, Any] = {
        "provider": "tgstat",
        "operation": "search",
        "query": q,
        "source": "premium-search",
        "count": len(results),
        "total_count": total,
        "truncated": truncated or (total is not None and total > MAX_POSTS),
        "cap": MAX_POSTS,
        "results": results,
    }
    return {key: value for key, value in out.items() if value is not None}


def _short_error(exc: BaseException) -> str:
    text = str(exc)
    for label in (
        "expired invite",
        "not a member",
        "no media",
        "deleted",
        "session busy",
        "too large",
    ):
        if label in text:
            return label
    return text.split(":")[-1].strip()[:200]


def _file_media(media: Any) -> dict[str, Any] | None:
    if not isinstance(media, dict):
        return None
    if media.get("type") in FILE_MEDIA_TYPES:
        return media
    return None


def enrich_hit(hit: dict[str, Any], get_message: GetMessage) -> dict[str, Any]:
    target = (hit.get("telegram") or {}).get("target") or hit.get("url")
    if not target:
        hit["has_media"] = False
        return hit
    try:
        got = get_message(str(target))
    except Exception as exc:
        return _mark_hit_error(hit, exc)
    return _apply_got(hit, got)


def _mark_hit_error(hit: dict[str, Any], exc: BaseException | str) -> dict[str, Any]:
    tg = dict(hit.get("telegram") or {})
    tg["has_media"] = False
    tg["error"] = _short_error(exc if isinstance(exc, BaseException) else Exception(str(exc)))
    hit["telegram"] = tg
    hit["has_media"] = False
    return hit


def _apply_got(hit: dict[str, Any], got: dict[str, Any] | None) -> dict[str, Any]:
    if not got:
        return _mark_hit_error(hit, "no media")
    if got.get("error") and not got.get("message") and not _file_media(got.get("media")):
        return _mark_hit_error(hit, str(got["error"]))
    media = got.get("media")
    if media is None and isinstance(got.get("message"), dict):
        media = got["message"].get("media")
    file_media = _file_media(media)
    is_file = file_media is not None
    tg = dict(hit.get("telegram") or {})
    target = tg.get("target") or hit.get("url")
    if target:
        tg["target"] = str(target)
    tg["has_media"] = is_file
    tg["private"] = bool(hit.get("private") or tg.get("private"))
    if file_media:
        tg["media"] = file_media
        if file_media.get("mime"):
            tg["mime"] = file_media["mime"]
        if file_media.get("name"):
            tg["name"] = file_media["name"]
        if file_media.get("size") is not None:
            tg["size"] = file_media["size"]
        hit["media"] = file_media.get("type")
    else:
        tg["media"] = media
        tg["has_media"] = False
    hit["telegram"] = tg
    hit["has_media"] = is_file
    if isinstance(got.get("message"), dict):
        hit["telegram_message"] = got["message"]
    return hit


def fetch_files(
    results: list[dict[str, Any]],
    *,
    get_message: GetMessage | None = None,
    download_file: TelegramDownload | None = None,
    get_many: GetMany | None = None,
    download_many: DownloadMany | None = None,
    output: str | None = None,
    media: str | None = None,
    include_private: bool = False,
    allow_large: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    jobs: int = DOWNLOAD_JOBS,
) -> list[dict[str, Any]]:
    want = (media or "").strip().lower() or None
    if want and want not in FILE_MEDIA_TYPES:
        raise ProviderHttpError(
            "tgstat", 0, f"media must be one of {', '.join(FILE_MEDIA_TYPES)}"
        )
    work: list[dict[str, Any]] = []
    for hit in results:
        private = bool(
            hit.get("private") or (hit.get("telegram") or {}).get("private")
        )
        if private and not include_private:
            continue
        work.append(hit)
    n_jobs = max(1, min(int(jobs or DOWNLOAD_JOBS), 8))
    if work and get_many is not None:
        targets = [
            str((hit.get("telegram") or {}).get("target") or hit.get("url") or "")
            for hit in work
        ]
        gots = get_many(targets, jobs=n_jobs)
        for hit, got in zip(work, gots):
            _apply_got(hit, got if isinstance(got, dict) else None)
    elif get_message is not None:
        for hit in work:
            enrich_hit(hit, get_message)
    if (download_file is None and download_many is None) or not output:
        return results
    dest_root = Path(output).expanduser()
    dest_root.mkdir(parents=True, exist_ok=True)

    pending: list[dict[str, Any]] = []
    for hit in work:
        tg = hit.get("telegram") or {}
        if not tg.get("has_media"):
            continue
        kind = tg.get("media")
        if isinstance(kind, dict):
            kind = kind.get("type")
        if want and kind != want:
            continue
        size = tg.get("size")
        if (
            not allow_large
            and isinstance(size, int)
            and size > max_bytes
        ):
            tg["skipped"] = "too large"
            hit["telegram"] = tg
            continue
        if not tg.get("target"):
            continue
        pending.append(hit)

    def _apply_saved(hit: dict[str, Any], saved: dict[str, Any] | None) -> None:
        tg = dict(hit.get("telegram") or {})
        if not saved or saved.get("error"):
            if saved and saved.get("error"):
                tg["error"] = _short_error(Exception(str(saved["error"])))
            hit["telegram"] = tg
            return
        tg["download"] = {
            "path": saved.get("path"),
            "filename": saved.get("filename"),
            "size": saved.get("size"),
        }
        hit["telegram"] = tg
        if isinstance(saved.get("message"), dict):
            hit["telegram_message"] = saved["message"]

    if not pending:
        return results
    if download_many is not None:
        pairs = [
            (str((hit.get("telegram") or {}).get("target")), str(dest_root))
            for hit in pending
        ]
        saved_list = download_many(pairs, jobs=n_jobs)
        for hit, saved in zip(pending, saved_list):
            _apply_saved(hit, saved if isinstance(saved, dict) else None)
        return results
    if download_file is None:
        return results
    for hit in pending:
        target = str((hit.get("telegram") or {}).get("target") or "")
        try:
            saved = download_file(target, str(dest_root))
        except Exception as exc:
            tg = dict(hit.get("telegram") or {})
            tg["error"] = _short_error(exc)
            hit["telegram"] = tg
            continue
        _apply_saved(hit, saved)
    return results


def mentions(
    query: str,
    *,
    cookie: str,
    group: str = "day",
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    **filters: Any,
) -> dict[str, Any]:
    q = _require_query(query)
    key = (group or "day").strip().lower()
    if key not in CHART_GROUPS:
        raise ProviderHttpError(
            "tgstat", 0, f"group must be one of {', '.join(CHART_GROUPS)}"
        )
    _search_fields(q, "x", **filters)
    csrf = _load_csrf(cookie, origin=origin, transport=transport, timeout=timeout)
    status, _, body = _execute(
        build_mentions_request(
            q, cookie=cookie, csrf=csrf, group=group, origin=origin, **filters
        ),
        transport=transport,
        timeout=timeout,
    )
    payload = _json_payload(status, body)
    if payload.get("status") != "ok":
        raise ProviderHttpError(
            "tgstat", status, str(payload.get("error") or "mentions chart failed")
        )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "provider": "tgstat",
        "operation": "mentions",
        "query": q,
        "group": (group or "day").strip().lower(),
        "count": list(data.get("count") or []),
        "reach": list(data.get("reach") or []),
    }


def _export_filename(headers: dict[str, str]) -> str:
    disposition = headers.get("content-disposition") or ""
    match = _FILENAME_RE.search(disposition)
    if match:
        name = os.path.basename(unquote(match.group(1).strip().strip('"')))
        if name:
            return name
    return "TGStat-Export.xlsx"


def export(
    query: str,
    *,
    cookie: str,
    output: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    **filters: Any,
) -> dict[str, Any]:
    q = _require_query(query)
    _search_fields(q, "x", **filters)
    csrf = _load_csrf(cookie, origin=origin, transport=transport, timeout=timeout)
    request = build_export_request(
        q, cookie=cookie, csrf=csrf, origin=origin, **filters
    )
    status, headers, body = _execute(
        request, transport=transport, timeout=timeout
    )
    if status >= 400:
        raise ProviderHttpError(
            "tgstat", status, body.decode("utf-8", errors="replace")[:500]
        )
    if not body:
        raise ProviderHttpError("tgstat", status, "empty export")
    filename = _export_filename(headers)
    dest = Path(output).expanduser() if output else Path.cwd() / filename
    if dest.exists() and dest.is_dir():
        dest = dest / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return {
        "provider": "tgstat",
        "operation": "export",
        "query": q,
        "path": str(dest.resolve()),
        "filename": dest.name,
        "content_type": headers.get("content-type", ""),
        "size": len(body),
    }


def sources(
    query: str,
    *,
    cookie: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
    **filters: Any,
) -> dict[str, Any]:
    q = _require_query(query)
    _search_fields(q, "x", **filters)
    csrf = _load_csrf(cookie, origin=origin, transport=transport, timeout=timeout)
    status, _, body = _execute(
        build_sources_request(
            q, cookie=cookie, csrf=csrf, origin=origin, **filters
        ),
        transport=transport,
        timeout=timeout,
    )
    html = body.decode("utf-8", errors="replace")
    if status >= 400:
        raise ProviderHttpError("tgstat", status, html[:500])
    results = parse_sources(html)
    return {
        "provider": "tgstat",
        "operation": "sources",
        "query": q,
        "count": len(results),
        "results": results,
    }


def catalogs() -> dict[str, Any]:
    return {
        "provider": "tgstat",
        "operation": "catalogs",
        "peer_types": list(PEER_TYPES),
        "sorts": list(SORTS),
        "source_sorts": list(SOURCE_SORTS),
        "forwards": list(FORWARDS),
        "views_ranges": list(VIEWS_RANGES),
        "chart_groups": list(CHART_GROUPS),
        "countries": dict(COUNTRIES),
        "languages": dict(LANGUAGES),
        "categories": dict(CATEGORIES),
    }


def download(
    target: str,
    *,
    output: str | None = None,
    telegram_download: TelegramDownload | None = None,
) -> dict[str, Any]:
    ident = (target or "").strip()
    if not ident:
        raise ProviderHttpError("tgstat", 0, "download needs a t.me link")
    url = canonical_telegram_url(ident)
    if not url:
        raise ProviderHttpError("tgstat", 0, "download needs a t.me link")
    if telegram_download is None:
        raise ProviderHttpError(
            "tgstat",
            0,
            "tgstat web search has no file bytes; log in with telegram and retry "
            "(public @channel, no join; private chat only if this account is a member)",
        )
    saved = telegram_download(url, output)
    return {
        "provider": "tgstat",
        "operation": "download",
        "source": "telegram",
        "url": url,
        "path": saved.get("path"),
        "filename": saved.get("filename"),
        "size": saved.get("size"),
        "telegram": saved,
    }
