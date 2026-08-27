from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from research_cli import __version__
from research_cli.errors import ProviderHttpError

_SYSTEM_CA_FILES = (
    "/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
)

USER_AGENT = f"research-cli/{__version__}"

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


def path_segment(value: str) -> str:
    return quote(value, safe="")


def encode_query(params: Mapping[str, Any]) -> str:
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            items.append((key, "true" if value else "false"))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if item is None or item == "":
                    continue
                items.append((key, str(item)))
        else:
            items.append((key, str(value)))
    return urlencode(items)


def with_query(url: str, params: Mapping[str, Any]) -> str:
    query = encode_query(params)
    if not query:
        return url
    return url + ("&" if "?" in url else "?") + query


def ssl_context() -> ssl.SSLContext:
    """CA bundle for urllib. Frozen PyInstaller builds do not ship certs."""
    cafile = (os.environ.get("SSL_CERT_FILE") or "").strip()
    capath = (os.environ.get("SSL_CERT_DIR") or "").strip()
    if cafile or capath:
        return ssl.create_default_context(
            cafile=cafile or None,
            capath=capath or None,
        )
    try:
        import certifi

        bundled = certifi.where()
        if bundled and Path(bundled).is_file():
            return ssl.create_default_context(cafile=bundled)
    except ImportError:
        pass
    frozen = bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
    if frozen:
        for candidate in _SYSTEM_CA_FILES:
            if Path(candidate).is_file():
                return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def urllib_transport(request: HttpRequest, timeout: float = 60.0) -> HttpResponse:
    req = urllib.request.Request(request.url, data=request.body, method=request.method)
    for key, value in request.headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=ssl_context()
        ) as response:
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
