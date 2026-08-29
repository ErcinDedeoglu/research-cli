from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode, urlparse

from research_cli.errors import ProviderHttpError
from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
    path_segment,
    with_query,
)

DEFAULT_ORIGIN = "https://oauth.reddit.com"
TOKEN_ORIGIN = "https://www.reddit.com"
TOKEN_PATH = "/api/v1/access_token"
SEARCH_PATH = "/search"
COMMENTS_PATH = "/comments"
_THREAD_SORT = {
    "best": "confidence",
    "confidence": "confidence",
    "top": "top",
    "new": "new",
    "controversial": "controversial",
    "old": "old",
    "qa": "qa",
}
_LISTING_SORTS = ("hot", "new", "top", "rising", "controversial")


def token_origin_for(origin: str) -> str:
    if origin.rstrip("/") == DEFAULT_ORIGIN:
        return TOKEN_ORIGIN
    return origin


def normalize_subreddit(value: str | None) -> str | None:
    if not value:
        return None
    name = value.strip()
    if name.lower().startswith("r/"):
        name = name[2:]
    name = name.strip("/")
    return name or None


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _oauth_headers(access_token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
    }


def build_token_request(
    *,
    client_id: str,
    client_secret: str,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    return HttpRequest(
        method="POST",
        url=join_url(token_origin_for(origin), TOKEN_PATH),
        headers={
            "Accept": "application/json",
            "Authorization": _basic_auth(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        body=urlencode({"grant_type": "client_credentials"}).encode("utf-8"),
    )


def parse_token_response(payload: Any) -> str:
    if isinstance(payload, dict):
        token = payload.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    raise ProviderHttpError("reddit", 200, "token response missing access_token")


def fetch_access_token(
    *,
    client_id: str,
    client_secret: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> str:
    request = build_token_request(
        client_id=client_id, client_secret=client_secret, origin=origin
    )
    payload = execute_json(
        request, provider="reddit", transport=transport, timeout=timeout
    )
    return parse_token_response(payload)


def build_search_request(
    query: str,
    *,
    access_token: str,
    sort: str = "relevance",
    time: str = "all",
    limit: int = 25,
    subreddit: str | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    sub = normalize_subreddit(subreddit)
    path = f"/r/{path_segment(sub)}/search" if sub else SEARCH_PATH
    url = with_query(
        join_url(origin, path),
        {
            "q": query,
            "sort": sort,
            "t": time,
            "limit": limit,
            "type": "link",
            "raw_json": 1,
            "restrict_sr": True if sub else None,
        },
    )
    return HttpRequest(
        method="GET",
        url=url,
        headers=_oauth_headers(access_token),
        body=None,
    )


def _permalink_url(post: dict[str, Any]) -> str | None:
    permalink = post.get("permalink")
    if isinstance(permalink, str) and permalink.strip():
        if permalink.startswith("http://") or permalink.startswith("https://"):
            return permalink
        if not permalink.startswith("/"):
            permalink = "/" + permalink
        return "https://www.reddit.com" + permalink
    url = post.get("url")
    if isinstance(url, str) and url.strip():
        return url
    return None


def _post_record(post: dict[str, Any]) -> dict[str, Any] | None:
    title = post.get("title")
    reddit_url = _permalink_url(post)
    if not title and not reddit_url:
        return None
    record: dict[str, Any] = {}
    post_id = post.get("id")
    if post_id not in (None, ""):
        record["id"] = post_id
    if title:
        record["title"] = title
    if reddit_url:
        record["url"] = reddit_url
    link_url = post.get("url")
    if (
        isinstance(link_url, str)
        and link_url
        and link_url != reddit_url
        and not link_url.startswith("https://www.reddit.com/")
    ):
        record["link_url"] = link_url
    for key in ("subreddit", "author"):
        value = post.get(key)
        if value not in (None, ""):
            record[key] = value
    for key in ("score", "num_comments", "created_utc"):
        if post.get(key) is not None:
            record[key] = post[key]
    selftext = post.get("selftext")
    if isinstance(selftext, str) and selftext.strip():
        record["description"] = selftext
    return record


def parse_search_response(payload: Any) -> dict[str, Any]:
    children: list[Any] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("children"), list):
            children = data["children"]
        elif isinstance(payload.get("children"), list):
            children = payload["children"]
        elif isinstance(payload.get("results"), list):
            children = payload["results"]
    results: list[dict[str, Any]] = []
    for child in children:
        post = child
        if isinstance(child, dict) and isinstance(child.get("data"), dict):
            post = child["data"]
        if not isinstance(post, dict):
            continue
        record = _post_record(post)
        if record:
            results.append(record)
    return {"provider": "reddit", "operation": "search", "results": results}


def search(
    query: str,
    *,
    client_id: str,
    client_secret: str,
    sort: str = "relevance",
    time: str = "all",
    limit: int = 25,
    subreddit: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    access_token = fetch_access_token(
        client_id=client_id,
        client_secret=client_secret,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    request = build_search_request(
        query,
        access_token=access_token,
        sort=sort,
        time=time,
        limit=limit,
        subreddit=subreddit,
        origin=origin,
    )
    payload = execute_json(
        request, provider="reddit", transport=transport, timeout=timeout
    )
    return parse_search_response(payload)


def parse_thread_ref(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ProviderHttpError("reddit", 0, "missing thread id or URL")
    path = raw
    if "://" in raw:
        parsed = urlparse(raw)
        path = parsed.path or raw
    if path.lower().startswith("t3_"):
        path = path[3:]
    parts = [item for item in path.split("/") if item]
    if "comments" in parts:
        index = parts.index("comments")
        if index + 1 < len(parts):
            post_id = parts[index + 1]
            if post_id.lower().startswith("t3_"):
                post_id = post_id[3:]
            if post_id:
                return post_id
    if len(parts) == 1:
        post_id = parts[0]
        if post_id.lower().startswith("t3_"):
            post_id = post_id[3:]
        if post_id:
            return post_id
    raise ProviderHttpError("reddit", 0, f"invalid thread id or URL: {value}")


def build_thread_request(
    target: str,
    *,
    access_token: str,
    sort: str = "best",
    limit: int = 50,
    depth: int | None = None,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    post_id = parse_thread_ref(target)
    reddit_sort = _THREAD_SORT.get(sort, sort)
    url = with_query(
        join_url(origin, f"{COMMENTS_PATH}/{path_segment(post_id)}"),
        {
            "sort": reddit_sort,
            "limit": limit,
            "depth": depth,
            "raw_json": 1,
        },
    )
    return HttpRequest(
        method="GET",
        url=url,
        headers=_oauth_headers(access_token),
        body=None,
    )


def _listing_children(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("children"), list):
            return data["children"]
        if isinstance(payload.get("children"), list):
            return payload["children"]
        return []
    if isinstance(payload, list):
        return payload
    return []


def _comment_record(comment: dict[str, Any], *, depth: int) -> dict[str, Any] | None:
    body = comment.get("body")
    author = comment.get("author")
    if body in (None, "") and author in (None, ""):
        return None
    record: dict[str, Any] = {"depth": depth}
    comment_id = comment.get("id")
    if comment_id not in (None, ""):
        record["id"] = comment_id
    if author not in (None, ""):
        record["author"] = author
    if isinstance(body, str) and body:
        record["body"] = body
    if comment.get("score") is not None:
        record["score"] = comment["score"]
    if comment.get("created_utc") is not None:
        record["created_utc"] = comment["created_utc"]
    permalink = _permalink_url(comment)
    if permalink:
        record["url"] = permalink
    return record


def _collect_comments(payload: Any, out: list[dict[str, Any]], *, depth: int) -> None:
    for child in _listing_children(payload):
        if not isinstance(child, dict):
            continue
        kind = child.get("kind")
        data = child.get("data") if isinstance(child.get("data"), dict) else child
        if not isinstance(data, dict) or kind == "more":
            continue
        if kind in (None, "t1") and "body" in data:
            record = _comment_record(data, depth=depth)
            if record:
                out.append(record)
            replies = data.get("replies")
            if replies not in (None, "", []):
                _collect_comments(replies, out, depth=depth + 1)


def parse_thread_response(payload: Any) -> dict[str, Any]:
    post_part: Any = None
    comments_part: Any = None
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict) and (
            first.get("kind") == "Listing" or isinstance(first.get("data"), dict)
        ):
            post_part = payload[0]
            comments_part = payload[1] if len(payload) > 1 else None
        else:
            comments_part = payload
    elif isinstance(payload, dict):
        post_part = payload.get("post", payload)
        comments_part = payload.get("comments")
    post: dict[str, Any] | None = None
    for child in _listing_children(post_part):
        if not isinstance(child, dict):
            continue
        data = child.get("data") if isinstance(child.get("data"), dict) else child
        if not isinstance(data, dict):  # pragma: no cover
            continue
        record = _post_record(data)
        if record:
            post = record
            break
    comments: list[dict[str, Any]] = []
    _collect_comments(comments_part, comments, depth=0)
    result = dict(post) if post else {}
    result["comments"] = comments
    return {"provider": "reddit", "operation": "thread", "results": [result]}


def thread(
    target: str,
    *,
    client_id: str,
    client_secret: str,
    sort: str = "best",
    limit: int = 50,
    depth: int | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    access_token = fetch_access_token(
        client_id=client_id,
        client_secret=client_secret,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    request = build_thread_request(
        target,
        access_token=access_token,
        sort=sort,
        limit=limit,
        depth=depth,
        origin=origin,
    )
    payload = execute_json(
        request, provider="reddit", transport=transport, timeout=timeout
    )
    return parse_thread_response(payload)


def build_subreddit_request(
    subreddit: str,
    *,
    access_token: str,
    sort: str = "hot",
    time: str = "all",
    limit: int = 25,
    origin: str = DEFAULT_ORIGIN,
) -> HttpRequest:
    sub = normalize_subreddit(subreddit)
    if not sub:
        raise ProviderHttpError("reddit", 0, "missing subreddit name")
    listing = sort if sort in _LISTING_SORTS else "hot"
    url = with_query(
        join_url(origin, f"/r/{path_segment(sub)}/{listing}"),
        {
            "t": time,
            "limit": limit,
            "raw_json": 1,
        },
    )
    return HttpRequest(
        method="GET",
        url=url,
        headers=_oauth_headers(access_token),
        body=None,
    )


def parse_subreddit_response(
    payload: Any, *, subreddit: str | None = None
) -> dict[str, Any]:
    parsed = parse_search_response(payload)
    parsed["operation"] = "subreddit"
    name = normalize_subreddit(subreddit)
    if name:
        parsed["subreddit"] = name
    return parsed


def list_subreddit(
    subreddit: str,
    *,
    client_id: str,
    client_secret: str,
    sort: str = "hot",
    time: str = "all",
    limit: int = 25,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    access_token = fetch_access_token(
        client_id=client_id,
        client_secret=client_secret,
        origin=origin,
        transport=transport,
        timeout=timeout,
    )
    request = build_subreddit_request(
        subreddit,
        access_token=access_token,
        sort=sort,
        time=time,
        limit=limit,
        origin=origin,
    )
    payload = execute_json(
        request, provider="reddit", transport=transport, timeout=timeout
    )
    return parse_subreddit_response(payload, subreddit=subreddit)
