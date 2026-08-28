from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlparse

from research_cli.errors import ProviderHttpError
from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
    path_segment,
    urllib_transport,
    with_query,
)

DEFAULT_ORIGIN = "https://sploitus.com"
SEARCH_PATH = "/search"
AUTOCOMPLETE_PATH = "/autocomplete"
PAGE_SIZE = 10
HUB_PAGE_SIZE = 50
SEARCH_TYPES = ("exploits", "tools")
SORTS = ("default", "date", "score")
FRONTEND_HEADER = "sploitus-frontend"
_MAX_HUB_PAGES = 20
_CVE_RE = re.compile(r"(CVE-\d{4}-\d+)", re.I)
_CARD_RE = re.compile(
    r"<a\b(?=[^>]*\bclass=vulnerability)"
    r"(?=[^>]*\bhref=(?P<q>['\"]?)(?P<href>/?(?:exploit\?id=|cve/)[^'\"\s>]+)(?P=q))"
    r"[^>]*>(?P<body>.*?)</a>",
    re.I | re.S,
)
_NEXT_RE = re.compile(
    r"<link href=(?P<href>\S+) rel=next>|"
    r"<a class=pagination__link href=(?P<href2>\S+) rel=next>",
    re.I,
)
_JSON_LD_RE = re.compile(
    r"<script type=?application/ld\+json>(.*?)</script>", re.I | re.S
)
_CODE_RE = re.compile(r"<code\b[^>]*>(.*?)</code>", re.I | re.S)
_METRIC_RE = re.compile(
    r"<dt class=card__metric-label>(.*?)</dt>"
    r"<dd class=card__metric-value>(.*?)</dd>",
    re.I | re.S,
)
_DESC_RE = re.compile(
    r'class="?vulnerability__description[^"]*"?>(.*?)</p>', re.I | re.S
)


def _json_headers(origin: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": origin.rstrip("/") + "/",
        "User-Agent": USER_AGENT,
        "X-Requested-With": FRONTEND_HEADER,
    }


def _page_headers(origin: str) -> dict[str, str]:
    return {
        "Accept": "text/html",
        "Referer": origin.rstrip("/") + "/",
        "User-Agent": USER_AGENT,
        "X-Requested-With": FRONTEND_HEADER,
    }


def _normalize_type(value: str | None) -> str:
    kind = (value or "exploits").strip().lower()
    if kind in ("tool", "hacktool", "hacktools"):
        return "tools"
    if kind in SEARCH_TYPES:
        return kind
    return "exploits"


def _normalize_sort(value: str | None) -> str:
    sort = (value or "default").strip().lower()
    return sort if sort in SORTS else "default"


def exploit_url(exploit_id: str) -> str:
    return f"{DEFAULT_ORIGIN}/exploit?id={quote(str(exploit_id), safe=':')}"


def normalize_exploit_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ProviderHttpError("sploitus", 0, "missing exploit id")
    parsed = urlparse(raw)
    if parsed.query:
        found = parse_qs(parsed.query).get("id")
        if found and found[0].strip():
            return found[0].strip()
    if "id=" in raw:
        return raw.split("id=", 1)[1].split("&", 1)[0].strip()
    return raw


def normalize_cve(value: str) -> str:
    raw = (value or "").strip()
    match = _CVE_RE.search(raw)
    if not match:
        raise ProviderHttpError("sploitus", 0, f"invalid CVE id: {value}")
    return match.group(1).upper()


def product_slug(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise ProviderHttpError("sploitus", 0, "missing product name")
    parsed = urlparse(name)
    path = parsed.path if parsed.scheme or parsed.netloc else name
    if "/product/" in path:
        path = path.rsplit("/product/", 1)[-1]
    path = path.split("/page/", 1)[0].strip("/")
    slug = path.lower().replace(" ", "-").strip("-")
    if not slug:
        raise ProviderHttpError("sploitus", 0, "missing product name")
    return slug


def build_search_request(
    query: str,
    *,
    search_type: str = "exploits",
    sort: str = "default",
    offset: int = 0,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload = {
        "type": _normalize_type(search_type),
        "sort": _normalize_sort(sort),
        "query": query,
        "offset": int(offset),
    }
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers=_json_headers(origin),
        body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )


def build_autocomplete_request(
    query: str, *, origin: str = DEFAULT_ORIGIN
) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=with_query(join_url(origin, AUTOCOMPLETE_PATH), {"query": query}),
        headers={
            "Accept": "application/json",
            "Referer": origin.rstrip("/") + "/",
            "User-Agent": USER_AGENT,
            "X-Requested-With": FRONTEND_HEADER,
        },
        body=None,
    )


def build_exploit_request(
    exploit_id: str, *, origin: str = DEFAULT_ORIGIN
) -> HttpRequest:
    ident = normalize_exploit_id(exploit_id)
    return HttpRequest(
        method="GET",
        url=with_query(join_url(origin, "/exploit"), {"id": ident}),
        headers=_page_headers(origin),
        body=None,
    )


def build_cve_request(cve_id: str, *, origin: str = DEFAULT_ORIGIN) -> HttpRequest:
    ident = normalize_cve(cve_id)
    return HttpRequest(
        method="GET",
        url=join_url(origin, f"/cve/{path_segment(ident)}"),
        headers=_page_headers(origin),
        body=None,
    )


def build_product_request(
    name: str, *, page: int = 1, origin: str = DEFAULT_ORIGIN
) -> HttpRequest:
    slug = product_slug(name)
    path = f"/product/{path_segment(slug)}"
    if int(page) > 1:
        path = f"{path}/page/{int(page)}"
    return HttpRequest(
        method="GET",
        url=join_url(origin, path),
        headers=_page_headers(origin),
        body=None,
    )


def build_latest_request(
    *, page: int = 1, origin: str = DEFAULT_ORIGIN
) -> HttpRequest:
    path = "/latest" if int(page) <= 1 else f"/latest/page/{int(page)}"
    return HttpRequest(
        method="GET",
        url=join_url(origin, path),
        headers=_page_headers(origin),
        body=None,
    )


def _item(item: Any, *, include_source: bool) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    exploit_id = item.get("id")
    title = item.get("title")
    if not exploit_id and not title:
        return None
    record: dict[str, Any] = {}
    if exploit_id:
        record["id"] = exploit_id
        record["url"] = exploit_url(str(exploit_id))
    if title:
        record["title"] = title
    href = item.get("href")
    if href:
        record["href"] = href
    source_type = item.get("type")
    if source_type:
        record["type"] = source_type
    published = item.get("published")
    if published:
        record["published"] = published
    score = item.get("score")
    if score is not None and score != "":
        record["score"] = score
    language = item.get("language")
    if language:
        record["language"] = language
    cves = item.get("cve_list")
    if isinstance(cves, list) and cves:
        record["cve"] = [cve for cve in cves if cve]
    elif item.get("cve_string"):
        record["cve"] = [item["cve_string"]]
    epss = item.get("epss_score")
    if epss is not None and epss != "":
        record["epss"] = epss
    description = item.get("description")
    if description:
        record["description"] = description
    download = item.get("download")
    if download:
        record["download"] = download
    views = item.get("view_count")
    if views is not None and views != "":
        record["views"] = views
    if include_source:
        source = item.get("source")
        if source:
            record["source"] = source
    return record


def parse_search_response(
    payload: Any,
    *,
    search_type: str = "exploits",
    sort: str = "default",
    include_source: bool = False,
) -> dict[str, Any]:
    items: list[Any] = []
    total = 0
    if isinstance(payload, dict):
        raw = payload.get("exploits")
        if isinstance(raw, list):
            items = raw
        total_raw = payload.get("exploits_total")
        if isinstance(total_raw, int):
            total = total_raw
        elif isinstance(total_raw, str) and total_raw.isdigit():
            total = int(total_raw)
    results: list[dict[str, Any]] = []
    for item in items:
        record = _item(item, include_source=include_source)
        if record:
            results.append(record)
    return {
        "provider": "sploitus",
        "operation": "search",
        "type": _normalize_type(search_type),
        "sort": _normalize_sort(sort),
        "total": total,
        "results": results,
    }


def search(
    query: str,
    *,
    search_type: str = "exploits",
    sort: str = "default",
    offset: int = 0,
    limit: int = 10,
    include_source: bool = False,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    kind = _normalize_type(search_type)
    sort_value = _normalize_sort(sort)
    want = max(0, int(limit))
    cursor = max(0, int(offset))
    collected: list[dict[str, Any]] = []
    total = 0
    if want == 0:
        return {
            "provider": "sploitus",
            "operation": "search",
            "type": kind,
            "sort": sort_value,
            "total": 0,
            "results": collected,
        }
    while len(collected) < want:
        request = build_search_request(
            query,
            search_type=kind,
            sort=sort_value,
            offset=cursor,
            origin=origin,
        )
        payload = execute_json(
            request, provider="sploitus", transport=transport, timeout=timeout
        )
        parsed = parse_search_response(
            payload,
            search_type=kind,
            sort=sort_value,
            include_source=include_source,
        )
        total = int(parsed.get("total") or 0)
        page = parsed["results"]
        if not page:
            break
        remaining = want - len(collected)
        collected.extend(page[:remaining])
        cursor += len(page)
        if len(page) < PAGE_SIZE:
            break
        if total and cursor >= total:
            break
    return {
        "provider": "sploitus",
        "operation": "search",
        "type": kind,
        "sort": sort_value,
        "total": total,
        "results": collected,
    }


def parse_autocomplete_response(payload: Any) -> dict[str, Any]:
    suggestions: list[str] = []
    if isinstance(payload, list):
        suggestions = [item for item in payload if isinstance(item, str) and item]
    results = [{"text": item} for item in suggestions]
    return {
        "provider": "sploitus",
        "operation": "autocomplete",
        "results": results,
    }


def autocomplete(
    query: str,
    *,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_autocomplete_request(query, origin=origin)
    payload = execute_json(
        request, provider="sploitus", transport=transport, timeout=timeout
    )
    return parse_autocomplete_response(payload)


def _execute_html(
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
        raise ProviderHttpError("sploitus", 0, str(exc)) from exc
    text = response.body.decode("utf-8", errors="replace")
    if response.status >= 400:
        raise ProviderHttpError("sploitus", response.status, text[:500])
    return text


def _plain(html: str) -> str:
    text = re.sub(r"<svg[\s\S]*?</svg>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _json_ld_graph(html: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    for blob in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            graph.extend(item for item in data["@graph"] if isinstance(item, dict))
        elif isinstance(data, dict):
            graph.append(data)
    return graph


def _card_id_and_kind(href: str) -> tuple[str | None, str | None]:
    raw = unescape(href)
    parsed = urlparse(raw)
    path = parsed.path or raw
    if "exploit" in path or parsed.query.startswith("id=") or "id=" in raw:
        ident = parse_qs(parsed.query).get("id") if parsed.query else None
        if ident:
            return ident[0], "exploit"
        if "id=" in raw:
            return raw.split("id=", 1)[1].split("&", 1)[0], "exploit"
    match = _CVE_RE.search(raw)
    if match:
        return match.group(1).upper(), "cve"
    return None, None


def _parse_cards(html: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in _CARD_RE.finditer(html):
        href = match.group("href")
        body = match.group("body")
        ident, kind = _card_id_and_kind(href)
        title_m = re.search(r"vulnerability__title>(.*?)</div>", body, re.I | re.S)
        title = _plain(title_m.group(1)) if title_m else _plain(body)
        count_m = re.search(r"vulnerability__count>([^<]+)", body, re.I)
        if count_m and title.endswith(count_m.group(1).strip()):
            title = title[: -len(count_m.group(1).strip())].strip()
        record: dict[str, Any] = {}
        if ident:
            record["id"] = ident
            if kind == "exploit":
                record["url"] = exploit_url(ident)
            elif kind == "cve":
                record["url"] = f"{DEFAULT_ORIGIN}/cve/{ident}"
        if title:
            record["title"] = title
        if count_m:
            record["count"] = _plain(count_m.group(1))
        meta_bits = [
            _plain(item)
            for item in re.findall(
                r"vulnerability__meta-item>(.*?)</span>", body, re.I | re.S
            )
        ]
        for bit in meta_bits:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", bit):
                record["published"] = bit
            elif re.match(r"(CVSS\s+)?\d+(\.\d+)?", bit):
                score = re.search(r"\d+(?:\.\d+)?", bit)
                if score:
                    try:
                        record["score"] = float(score.group(0))
                    except ValueError:
                        record["score"] = score.group(0)
            elif bit and bit.lower() not in {"tool"}:
                if "author" not in record and not bit.upper().startswith("CVSS"):
                    if not re.match(r"^\d", bit):
                        record["author"] = bit
        tags = [
            _plain(tag)
            for tag in re.findall(r"vulnerability__tag>([^<]+)", body, re.I)
        ]
        tags = [tag for tag in tags if tag]
        if tags:
            record["tag"] = tags[0] if len(tags) == 1 else tags
        if record.get("id") or record.get("title"):
            results.append(record)
    return results


def _parse_metrics(html: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for label_html, value_html in _METRIC_RE.findall(html):
        label = _plain(label_html)
        value = _plain(value_html)
        if label and value:
            metrics[label] = value
    return metrics


def _next_path(html: str) -> str | None:
    match = _NEXT_RE.search(html)
    if not match:
        return None
    href = (match.group("href") or match.group("href2") or "").strip().strip("'\"")
    if not href:
        return None
    parsed = urlparse(href)
    path = parsed.path or href
    if parsed.query:
        path = path + "?" + parsed.query
    if not path.startswith("/"):
        path = "/" + path
    return path


def parse_exploit_html(html: str, *, exploit_id: str | None = None) -> dict[str, Any]:
    ident = normalize_exploit_id(exploit_id) if exploit_id else None
    graph = _json_ld_graph(html)
    article = next((item for item in graph if item.get("@type") == "TechArticle"), {})
    headline = article.get("headline") or article.get("name")
    description = article.get("description")
    published = article.get("datePublished")
    modified = article.get("dateModified")
    language = None
    href = None
    has_part = article.get("hasPart")
    if isinstance(has_part, dict):
        language = has_part.get("programmingLanguage")
        href = has_part.get("codeRepository")
    lang_m = re.search(r"data-lang=([^\s>]+)", html, re.I)
    if lang_m and not language:
        language = lang_m.group(1).strip("\"'")
    about = article.get("about")
    cves: list[str] = []
    if isinstance(about, list):
        for item in about:
            if isinstance(item, dict):
                found = item.get("identifier") or item.get("name")
                if found:
                    try:
                        cves.append(normalize_cve(str(found)))
                    except ProviderHttpError:
                        continue
    elif isinstance(about, dict):
        found = about.get("identifier") or about.get("name")
        if found:
            try:
                cves.append(normalize_cve(str(found)))
            except ProviderHttpError:
                pass
    views = None
    stats = article.get("interactionStatistic")
    if isinstance(stats, dict):
        views = stats.get("userInteractionCount")
    elif isinstance(stats, list) and stats and isinstance(stats[0], dict):
        views = stats[0].get("userInteractionCount")
    code_m = _CODE_RE.search(html)
    source = unescape(code_m.group(1)) if code_m else None
    if ident is None:
        url = article.get("url")
        if isinstance(url, str) and "id=" in url:
            ident = normalize_exploit_id(url)
    record: dict[str, Any] = {}
    if ident:
        record["id"] = ident
        record["url"] = exploit_url(ident)
    if headline:
        record["title"] = headline
    if href:
        record["href"] = href
    type_m = re.search(r"logo logo_([a-z0-9_-]+)", html, re.I)
    if type_m:
        record["type"] = type_m.group(1)
    if published:
        record["published"] = published
    if modified:
        record["modified"] = modified
    if language:
        record["language"] = language
    if cves:
        record["cve"] = cves
    if views is not None:
        record["views"] = views
    if description:
        record["description"] = description
    if source:
        record["source"] = source
    if not record:
        raise ProviderHttpError("sploitus", 200, "exploit page missing record")
    return {
        "provider": "sploitus",
        "operation": "exploit",
        "results": [record],
    }


def parse_cve_html(html: str, *, cve_id: str | None = None) -> dict[str, Any]:
    ident = normalize_cve(cve_id) if cve_id else None
    graph = _json_ld_graph(html)
    page = next(
        (item for item in graph if item.get("@type") == "CollectionPage"), {}
    )
    about = page.get("about") if isinstance(page.get("about"), dict) else {}
    if ident is None and about.get("identifier"):
        ident = normalize_cve(str(about["identifier"]))
    description = about.get("description")
    if not description:
        desc_m = _DESC_RE.search(html)
        if desc_m:
            description = _plain(desc_m.group(1))
    nvd = about.get("url")
    results = _parse_cards(html)
    payload: dict[str, Any] = {
        "provider": "sploitus",
        "operation": "cve",
        "total": len(results),
        "results": results,
    }
    if ident:
        payload["cve"] = ident
        payload["url"] = f"{DEFAULT_ORIGIN}/cve/{ident}"
    if description:
        payload["description"] = description
    if nvd:
        payload["nvd"] = nvd
    metrics = _parse_metrics(html)
    if metrics:
        payload["metrics"] = metrics
    entity = page.get("mainEntity")
    if isinstance(entity, dict) and isinstance(entity.get("numberOfItems"), int):
        payload["total"] = entity["numberOfItems"]
    return payload


def parse_product_html(html: str, *, name: str | None = None) -> dict[str, Any]:
    slug = product_slug(name) if name else None
    graph = _json_ld_graph(html)
    page = next(
        (item for item in graph if item.get("@type") == "CollectionPage"), {}
    )
    about = page.get("about") if isinstance(page.get("about"), dict) else {}
    title = page.get("name") or about.get("name")
    results = _parse_cards(html)
    payload: dict[str, Any] = {
        "provider": "sploitus",
        "operation": "product",
        "results": results,
    }
    if slug:
        payload["product"] = slug
        payload["url"] = f"{DEFAULT_ORIGIN}/product/{slug}"
    if title:
        payload["title"] = title
    metrics = _parse_metrics(html)
    if metrics:
        payload["metrics"] = metrics
    entity = page.get("mainEntity")
    if isinstance(entity, dict) and isinstance(entity.get("numberOfItems"), int):
        payload["total"] = entity["numberOfItems"]
    else:
        payload["total"] = len(results)
    return payload


def parse_latest_html(html: str) -> dict[str, Any]:
    results = _parse_cards(html)
    return {
        "provider": "sploitus",
        "operation": "latest",
        "results": results,
    }


def exploit(
    exploit_id: str,
    *,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    ident = normalize_exploit_id(exploit_id)
    request = build_exploit_request(ident, origin=origin)
    html = _execute_html(request, transport=transport, timeout=timeout)
    return parse_exploit_html(html, exploit_id=ident)


def _collect_hub_pages(
    first: HttpRequest,
    *,
    parse,
    limit: int,
    origin: str,
    transport: Transport | None,
    timeout: float,
) -> tuple[list[dict[str, Any]], str]:
    want = max(0, int(limit))
    collected: list[dict[str, Any]] = []
    html = ""
    request: HttpRequest | None = first
    pages = 0
    while request is not None and pages < _MAX_HUB_PAGES:
        page_html = _execute_html(request, transport=transport, timeout=timeout)
        if not html:
            html = page_html
        parsed = parse(page_html)
        page_items = parsed.get("results") or []
        pages += 1
        if want == 0:
            break
        remaining = want - len(collected)
        collected.extend(page_items[:remaining])
        if len(collected) >= want:
            break
        if len(page_items) == 0:
            break
        next_path = _next_path(page_html)
        if not next_path:
            break
        request = HttpRequest(
            method="GET",
            url=join_url(origin, next_path),
            headers=_page_headers(origin),
            body=None,
        )
    return collected, html


def cve(
    cve_id: str,
    *,
    limit: int = 100,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    ident = normalize_cve(cve_id)
    request = build_cve_request(ident, origin=origin)
    html = _execute_html(request, transport=transport, timeout=timeout)
    parsed = parse_cve_html(html, cve_id=ident)
    want = max(0, int(limit))
    if want:
        parsed["results"] = parsed["results"][:want]
    return parsed


def product(
    name: str,
    *,
    limit: int = 50,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    slug = product_slug(name)
    request = build_product_request(slug, origin=origin)
    results, html = _collect_hub_pages(
        request,
        parse=lambda body: parse_product_html(body, name=slug),
        limit=limit,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    parsed = parse_product_html(html, name=slug)
    parsed["results"] = results
    if not parsed.get("total"):
        parsed["total"] = len(results)
    return parsed


def latest(
    *,
    limit: int = 50,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_latest_request(origin=origin)
    results, _html = _collect_hub_pages(
        request,
        parse=parse_latest_html,
        limit=limit,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    return {
        "provider": "sploitus",
        "operation": "latest",
        "results": results,
    }
