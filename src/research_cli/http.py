from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from research_cli.errors import ProviderHttpError

USER_AGENT = "research-cli/0.1.0"

Transport = Callable[["HttpRequest"], "HttpResponse"]


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


def join_url(origin: str, path: str) -> str:
    origin = origin.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return origin + path


def urllib_transport(request: HttpRequest, timeout: float = 60.0) -> HttpResponse:
    req = urllib.request.Request(request.url, data=request.body, method=request.method)
    for key, value in request.headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return HttpResponse(
                status=int(response.status),
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        headers = dict(exc.headers.items()) if exc.headers is not None else {}
        return HttpResponse(status=int(exc.code), headers=headers, body=body)


def execute_json(
    request: HttpRequest,
    *,
    provider: str,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> Any:
    send = transport if transport is not None else (
        lambda req: urllib_transport(req, timeout=timeout)
    )
    try:
        response = send(request)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderHttpError(provider, 0, str(exc)) from exc
    text = response.body.decode("utf-8", errors="replace")
    if response.status >= 400:
        raise ProviderHttpError(provider, response.status, text)
    if not text.strip():
        raise ProviderHttpError(provider, response.status, "empty response body")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderHttpError(
            provider, response.status, f"invalid JSON: {text[:500]}"
        ) from exc
