from __future__ import annotations

import json
from typing import Any

from research_cli.errors import ProviderHttpError
from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
)

DEFAULT_ORIGIN = "https://api.firecrawl.dev"
SCRAPE_PATH = "/v2/scrape"
SEARCH_PATH = "/v2/search"
MAP_PATH = "/v2/map"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }


def reject_unsuccessful(payload: Any, operation: str) -> None:
    if isinstance(payload, dict) and payload.get("success") is False:
        detail = payload.get("error") or payload.get("message") or payload
        raise ProviderHttpError("firecrawl", 200, f"{operation} failed: {detail}")


def build_scrape_request(
    url: str,
    *,
    api_key: str,
    formats: list[str] | None = None,
    only_main_content: bool | None = None,
    max_age: int | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {"url": url, "formats": formats or ["markdown"]}
    if only_main_content is not None:
        payload["onlyMainContent"] = only_main_content
    if max_age is not None:
        payload["maxAge"] = max_age
    return HttpRequest(
        method="POST",
        url=join_url(origin, SCRAPE_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def build_search_request(
    query: str,
    *,
    api_key: str,
    limit: int = 10,
    categories: list[str] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    scrape: bool = False,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {"query": query, "limit": limit}
    if categories:
        payload["categories"] = categories
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    if scrape:
        payload["scrapeOptions"] = {"formats": ["markdown"]}
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def build_map_request(
    url: str,
    *,
    api_key: str,
    search: str | None = None,
    limit: int = 50,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {"url": url, "limit": limit}
    if search:
        payload["search"] = search
    return HttpRequest(
        method="POST",
        url=join_url(origin, MAP_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def parse_scrape_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "scrape")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    record: dict[str, Any] = {}
    title = metadata.get("title")
    url = metadata.get("url") or metadata.get("sourceURL") or data.get("url")
    if title:
        record["title"] = title
    if url:
        record["url"] = url
    for key in ("markdown", "html", "rawHtml", "summary", "json", "links"):
        value = data.get(key)
        if value not in (None, "", []):
            record[key] = value
    if not record.get("markdown") and data.get("content"):
        record["markdown"] = data["content"]
    results = [record] if record else []
    return {"provider": "firecrawl", "operation": "scrape", "results": results}


def parse_search_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "search")
    data: Any = payload.get("data") if isinstance(payload, dict) else payload
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("web", "news", "developer", "results"):
            value = data.get(key)
            if isinstance(value, list):
                items = value
                break
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            continue
        record: dict[str, Any] = {"url": url}
        title = item.get("title")
        snippet = item.get("description") or item.get("snippet")
        markdown = item.get("markdown")
        if title:
            record["title"] = title
        if snippet:
            record["snippet"] = snippet
        if markdown:
            record["markdown"] = markdown
        results.append(record)
    return {"provider": "firecrawl", "operation": "search", "results": results}


def parse_map_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "map")
    raw = payload.get("links") if isinstance(payload, dict) else None
    if raw is None and isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        raw = payload["data"].get("links")
    if not isinstance(raw, list):
        raw = []
    results: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str) and item:
            results.append({"url": item})
            continue
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            continue
        record: dict[str, Any] = {"url": url}
        if item.get("title"):
            record["title"] = item["title"]
        if item.get("description"):
            record["description"] = item["description"]
        results.append(record)
    return {"provider": "firecrawl", "operation": "map", "results": results}


def scrape(
    url: str,
    *,
    api_key: str,
    formats: list[str] | None = None,
    only_main_content: bool | None = None,
    max_age: int | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_scrape_request(
        url,
        api_key=api_key,
        formats=formats,
        only_main_content=only_main_content,
        max_age=max_age,
        origin=origin,
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_scrape_response(payload)


def search(
    query: str,
    *,
    api_key: str,
    limit: int = 10,
    categories: list[str] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    scrape: bool = False,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query,
        api_key=api_key,
        limit=limit,
        categories=categories,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        scrape=scrape,
        origin=origin,
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)


def map_site(
    url: str,
    *,
    api_key: str,
    search: str | None = None,
    limit: int = 50,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_map_request(
        url, api_key=api_key, search=search, limit=limit, origin=origin
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_map_response(payload)
