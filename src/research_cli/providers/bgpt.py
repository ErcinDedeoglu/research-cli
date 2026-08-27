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

DEFAULT_ORIGIN = "https://bgpt.pro"
SEARCH_PATH = "/api/mcp-search"
_PAPER_FIELDS = (
    "title",
    "doi",
    "url",
    "authors",
    "journal",
    "year",
    "abstract",
    "central_claim",
)


def build_search_request(
    query: str,
    *,
    num_results: int = 10,
    days_back: int | None = None,
    api_key: str | None = None,
    output_format: str = "evidence",
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    payload: dict[str, Any] = {
        "query": query,
        "num_results": num_results,
        "output_format": output_format,
    }
    if days_back is not None:
        payload["days_back"] = days_back
    if api_key:
        payload["api_key"] = api_key
    return HttpRequest(
        method="POST",
        url=join_url(origin, SEARCH_PATH),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        body=json.dumps(payload).encode("utf-8"),
    )


def parse_search_response(payload: Any) -> dict[str, Any]:
    items: list[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("results", "papers", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        record = {
            key: item[key]
            for key in _PAPER_FIELDS
            if item.get(key) not in (None, "")
        }
        if "title" not in record and "doi" not in record:
            for key in ("id", "paper_id", "pmid"):
                if item.get(key) not in (None, ""):
                    record[key] = item[key]
                    break
        if record:
            results.append(record)
    return {"provider": "bgpt", "operation": "search", "results": results}


def search_papers(
    query: str,
    *,
    num_results: int = 10,
    days_back: int | None = None,
    api_key: str | None = None,
    output_format: str = "evidence",
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query,
        num_results=num_results,
        days_back=days_back,
        api_key=api_key,
        output_format=output_format,
        origin=origin,
    )
    payload = execute_json(
        request, provider="bgpt", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)
