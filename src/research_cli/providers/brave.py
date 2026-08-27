from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
)

DEFAULT_ORIGIN = "https://api.search.brave.com"
SEARCH_PATH = "/res/v1/web/search"


def build_search_request(
    query: str,
    *,
    api_key: str,
    count: int = 10,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    url = join_url(origin, SEARCH_PATH) + "?" + urlencode({"q": query, "count": count})
    return HttpRequest(
        method="GET",
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-Subscription-Token": api_key,
        },
        body=None,
    )


def parse_search_response(payload: Any) -> dict[str, Any]:
    items: list[Any] = []
    if isinstance(payload, dict):
        web = payload.get("web")
        if isinstance(web, dict) and isinstance(web.get("results"), list):
            items = web["results"]
        elif isinstance(payload.get("results"), list):
            items = payload["results"]
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        if not title and not url:
            continue
        record: dict[str, Any] = {}
        if title:
            record["title"] = title
        if url:
            record["url"] = url
        description = item.get("description") or item.get("snippet")
        if description:
            record["description"] = description
        results.append(record)
    return {"provider": "brave", "operation": "search", "results": results}


def web_search(
    query: str,
    *,
    api_key: str,
    count: int = 10,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query, api_key=api_key, count=count, origin=origin
    )
    payload = execute_json(
        request, provider="brave search", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)
