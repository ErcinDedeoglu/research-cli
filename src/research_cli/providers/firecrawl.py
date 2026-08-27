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


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }


def build_scrape_request(
    url: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload = {"url": url, "formats": ["markdown"]}
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
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload = {"query": query, "limit": limit}
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def _reject_unsuccessful(payload: Any, operation: str) -> None:
    if isinstance(payload, dict) and payload.get("success") is False:
        detail = payload.get("error") or payload.get("message") or payload
        raise ProviderHttpError("firecrawl", 200, f"{operation} failed: {detail}")


def parse_scrape_response(payload: Any) -> dict[str, Any]:
    _reject_unsuccessful(payload, "scrape")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    record: dict[str, Any] = {}
    title = metadata.get("title")
    url = metadata.get("url") or metadata.get("sourceURL") or data.get("url")
    markdown = data.get("markdown") or data.get("content")
    if title:
        record["title"] = title
    if url:
        record["url"] = url
    if markdown:
        record["markdown"] = markdown
    results = [record] if record else []
    return {"provider": "firecrawl", "operation": "scrape", "results": results}


def parse_search_response(payload: Any) -> dict[str, Any]:
    _reject_unsuccessful(payload, "search")
    data: Any = payload.get("data") if isinstance(payload, dict) else payload
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("web", "news", "results"):
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
        snippet = item.get("description") or item.get("snippet") or item.get("markdown")
        if title:
            record["title"] = title
        if snippet:
            record["snippet"] = snippet
        results.append(record)
    return {"provider": "firecrawl", "operation": "search", "results": results}


def scrape(
    url: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_scrape_request(url, api_key=api_key, origin=origin)
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_scrape_response(payload)


def search(
    query: str,
    *,
    api_key: str,
    limit: int = 10,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query, api_key=api_key, limit=limit, origin=origin
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)
