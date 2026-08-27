from __future__ import annotations

import json
from typing import Any

from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
)

DEFAULT_ORIGIN = "https://api.exa.ai"
SEARCH_PATH = "/search"
CONTENTS_PATH = "/contents"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "x-api-key": api_key,
    }


def build_search_request(
    query: str,
    *,
    api_key: str,
    num_results: int = 10,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    category: str | None = None,
    start_published: str | None = None,
    end_published: str | None = None,
    highlights: bool = False,
    text: bool = False,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {
        "query": query,
        "type": "auto",
        "numResults": num_results,
    }
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    if category:
        payload["category"] = category
    if start_published:
        payload["startPublishedDate"] = start_published
    if end_published:
        payload["endPublishedDate"] = end_published
    contents: dict[str, Any] = {}
    if highlights:
        contents["highlights"] = True
    if text:
        contents["text"] = True
    if contents:
        payload["contents"] = contents
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def build_contents_request(
    url: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {"urls": [url], "text": True, "highlights": True}
    return HttpRequest(
        method="POST",
        url=join_url(origin, CONTENTS_PATH),
        headers=_headers(api_key),
        body=json.dumps(payload).encode("utf-8"),
    )


def _exa_hit(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = item.get("title")
    url = item.get("url") or item.get("id")
    text = item.get("text")
    highlights = item.get("highlights")
    if not title and not url and not text and not highlights:
        return None
    record: dict[str, Any] = {}
    if title:
        record["title"] = title
    if url:
        record["url"] = url
    if text:
        record["text"] = text
    if highlights:
        record["highlights"] = highlights
    return record


def parse_search_response(payload: Any) -> dict[str, Any]:
    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        items = []
    results = [hit for hit in (_exa_hit(item) for item in items) if hit]
    return {"provider": "exa", "operation": "search", "results": results}


def parse_contents_response(payload: Any) -> dict[str, Any]:
    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        items = []
    results = [hit for hit in (_exa_hit(item) for item in items) if hit]
    return {"provider": "exa", "operation": "contents", "results": results}


def search(
    query: str,
    *,
    api_key: str,
    num_results: int = 10,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    category: str | None = None,
    start_published: str | None = None,
    end_published: str | None = None,
    highlights: bool = False,
    text: bool = False,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query,
        api_key=api_key,
        num_results=num_results,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        category=category,
        start_published=start_published,
        end_published=end_published,
        highlights=highlights,
        text=text,
        origin=origin,
    )
    payload = execute_json(
        request, provider="exa", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)


def contents(
    url: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_contents_request(url, api_key=api_key, origin=origin)
    payload = execute_json(
        request, provider="exa", transport=transport, timeout=timeout
    )
    return parse_contents_response(payload)
