from __future__ import annotations

from typing import Any

from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
    path_segment,
    with_query,
)
from research_cli.providers.firecrawl import DEFAULT_ORIGIN, reject_unsuccessful

PAPERS_PATH = "/v2/search/research/papers"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": USER_AGENT,
    }


def _paper_url(origin: str, paper_id: str, suffix: str = "") -> str:
    return join_url(origin, f"{PAPERS_PATH}/{path_segment(paper_id)}{suffix}")


def build_search_request(
    query: str,
    *,
    api_key: str,
    k: int = 40,
    authors: str | None = None,
    categories: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    url = with_query(
        join_url(origin, PAPERS_PATH),
        {
            "query": query,
            "k": k,
            "authors": authors,
            "categories": categories,
            "from": from_date,
            "to": to_date,
        },
    )
    return HttpRequest(method="GET", url=url, headers=_headers(api_key), body=None)


def build_inspect_request(
    paper_id: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=_paper_url(origin, paper_id),
        headers=_headers(api_key),
        body=None,
    )


def build_read_request(
    paper_id: str,
    question: str,
    *,
    api_key: str,
    k: int = 4,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    url = with_query(_paper_url(origin, paper_id), {"query": question, "k": k})
    return HttpRequest(method="GET", url=url, headers=_headers(api_key), body=None)


def build_related_request(
    paper_id: str,
    intent: str,
    *,
    api_key: str,
    mode: str = "similar",
    k: int = 40,
    anchors: list[str] | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    url = with_query(
        _paper_url(origin, paper_id, "/similar"),
        {"intent": intent, "mode": mode, "k": k, "anchor": anchors},
    )
    return HttpRequest(method="GET", url=url, headers=_headers(api_key), body=None)


def _paper_record(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    record: dict[str, Any] = {}
    for key in (
        "paperId",
        "primaryId",
        "title",
        "abstract",
        "authors",
        "categories",
        "score",
        "ids",
        "createdDate",
        "updateDate",
    ):
        value = item.get(key)
        if value not in (None, "", []):
            record[key] = value
    return record or None


def parse_search_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "papers search")
    raw = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raw = []
    results = [hit for hit in (_paper_record(item) for item in raw) if hit]
    return {"provider": "firecrawl", "operation": "papers-search", "results": results}


def parse_inspect_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "papers inspect")
    paper = payload.get("paper") if isinstance(payload, dict) else None
    record = _paper_record(paper) or _paper_record(payload) or {}
    results = [record] if record else []
    return {"provider": "firecrawl", "operation": "papers-inspect", "results": results}


def parse_read_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "papers read")
    raw: Any = None
    if isinstance(payload, dict):
        raw = payload.get("passages") or payload.get("results")
        if raw is None and isinstance(payload.get("paper"), dict):
            raw = payload["paper"].get("passages")
    if not isinstance(raw, list):
        raw = []
    results: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str) and item:
            results.append({"text": item})
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("passage") or item.get("content")
        if not text:
            continue
        record: dict[str, Any] = {"text": text}
        if item.get("score") is not None:
            record["score"] = item["score"]
        results.append(record)
    return {"provider": "firecrawl", "operation": "papers-read", "results": results}


def parse_related_response(payload: Any) -> dict[str, Any]:
    reject_unsuccessful(payload, "papers related")
    raw = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raw = []
    results = [hit for hit in (_paper_record(item) for item in raw) if hit]
    return {"provider": "firecrawl", "operation": "papers-related", "results": results}


def search_papers(
    query: str,
    *,
    api_key: str,
    k: int = 40,
    authors: str | None = None,
    categories: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_search_request(
        query,
        api_key=api_key,
        k=k,
        authors=authors,
        categories=categories,
        from_date=from_date,
        to_date=to_date,
        origin=origin,
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)


def inspect_paper(
    paper_id: str,
    *,
    api_key: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_inspect_request(paper_id, api_key=api_key, origin=origin)
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_inspect_response(payload)


def read_paper(
    paper_id: str,
    question: str,
    *,
    api_key: str,
    k: int = 4,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_read_request(
        paper_id, question, api_key=api_key, k=k, origin=origin
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_read_response(payload)


def related_papers(
    paper_id: str,
    intent: str,
    *,
    api_key: str,
    mode: str = "similar",
    k: int = 40,
    anchors: list[str] | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request = build_related_request(
        paper_id,
        intent,
        api_key=api_key,
        mode=mode,
        k=k,
        anchors=anchors,
        origin=origin,
    )
    payload = execute_json(
        request, provider="firecrawl", transport=transport, timeout=timeout
    )
    return parse_related_response(payload)
