from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, unquote

from research_cli.errors import ProviderHttpError
from research_cli.http import (
    USER_AGENT,
    HttpRequest,
    Transport,
    execute_json,
    join_url,
    urllib_transport,
)

DEFAULT_ORIGIN = "https://malpedia.caad.fkie.fraunhofer.de"
TLPS = ("white", "green", "amber")
_HASH_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILENAME_RE = re.compile(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", re.I)
_BIB_ENTRY_RE = re.compile(
    r"@(?P<kind>\w+)\s*\{\s*(?P<key>[^,]+),\s*(?P<body>.*?)\n\}",
    re.S,
)
_BIB_FIELD_RE = re.compile(
    r"(?P<name>\w+)\s*=\s*\{(?:\{(?P<inner>[^{}]*)\}|(?P<value>[^{}]*))\}"
)


def _segment(value: str) -> str:
    return quote((value or "").strip(), safe=".-_")


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _headers(token: str | None, accept: str = "application/json, */*") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"apitoken {token}"
    return headers


def build_get_request(
    path: str,
    *,
    origin: str = DEFAULT_ORIGIN,
    token: str | None = None,
    accept: str = "application/json, */*",
) -> HttpRequest:
    if not path.startswith("/"):
        path = "/" + path
    return HttpRequest(
        method="GET",
        url=join_url(origin, path),
        headers=_headers(token, accept),
        body=None,
    )


def _execute_body(
    request: HttpRequest,
    *,
    transport: Transport | None,
    timeout: float,
) -> tuple[dict[str, str], bytes]:
    send = transport if transport is not None else (
        lambda req: urllib_transport(req, timeout=timeout)
    )
    try:
        response = send(request)
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderHttpError("malpedia", 0, str(exc)) from exc
    if response.status >= 400:
        text = response.body.decode("utf-8", errors="replace")
        raise ProviderHttpError("malpedia", response.status, text[:500])
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    return headers, response.body


def _loads(body: bytes) -> Any:
    text = body.decode("utf-8", errors="replace")
    if not text.strip():
        raise ProviderHttpError("malpedia", 200, "empty response body")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderHttpError(
            "malpedia", 200, f"invalid JSON: {text[:500]}"
        ) from exc


def _json(
    path: str,
    *,
    origin: str,
    token: str | None,
    transport: Transport | None,
    timeout: float,
) -> Any:
    return execute_json(
        build_get_request(path, origin=origin, token=token),
        provider="malpedia",
        transport=transport,
        timeout=timeout,
    )


def _fetch(
    path: str,
    *,
    origin: str,
    token: str | None,
    transport: Transport | None,
    timeout: float,
    accept: str = "application/json, */*",
) -> tuple[HttpRequest, dict[str, str], bytes]:
    request = build_get_request(path, origin=origin, token=token, accept=accept)
    headers, body = _execute_body(request, transport=transport, timeout=timeout)
    return request, headers, body


def _filename(headers: dict[str, str], default: str) -> str:
    disposition = headers.get("content-disposition") or ""
    match = _FILENAME_RE.search(disposition)
    if match:
        name = os.path.basename(unquote(match.group(1).strip().strip('"')))
        if name:
            return name
    return default


def _write_artifact(
    body: bytes,
    *,
    output: str | None,
    filename: str,
) -> tuple[str, str]:
    dest = Path(output).expanduser() if output else Path.cwd() / filename
    if dest.exists() and dest.is_dir():
        dest = dest / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return str(dest.resolve()), dest.name


def _artifact(
    request: HttpRequest,
    headers: dict[str, str],
    body: bytes,
    *,
    operation: str,
    output: str | None,
    filename: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path, name = _write_artifact(body, output=output, filename=_filename(headers, filename))
    record: dict[str, Any] = {
        "provider": "malpedia",
        "operation": operation,
        "url": request.url,
        "filename": name,
        "path": path,
        "content_type": headers.get("content-type", ""),
        "size": len(body),
    }
    if extra:
        record.update(extra)
    return record


def _family_url(origin: str, ident: str) -> str:
    return f"{origin.rstrip('/')}/details/{ident}"


def _actor_url(origin: str, ident: str) -> str:
    return f"{origin.rstrip('/')}/actor/{ident}"


def normalize_tlp(value: str) -> str:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw.startswith("tlp_"):
        raw = raw[4:]
    if raw not in TLPS:
        raise ProviderHttpError(
            "malpedia",
            400,
            f"tlp must be one of {', '.join(TLPS)} (got {value!r})",
        )
    return f"tlp_{raw}"


def parse_bibtex(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for match in _BIB_ENTRY_RE.finditer(text or ""):
        item = {
            "key": match.group("key").strip(),
            "kind": match.group("kind").strip(),
        }
        for field in _BIB_FIELD_RE.finditer(match.group("body")):
            value = field.group("inner")
            if value is None:
                value = field.group("value") or ""
            item[field.group("name")] = value.strip()
        entries.append(item)
    return entries


def _find_hits(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    hits: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        alts = item.get("alt_names")
        hits.append(
            {
                "name": name,
                "alt_names": [str(a) for a in alts] if isinstance(alts, list) else [],
            }
        )
    return hits


def parse_family(payload: Any, *, ident: str, origin: str) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    attribution = data.get("attribution")
    return {
        "provider": "malpedia",
        "operation": "family",
        "id": ident,
        "common_name": data.get("common_name") or ident,
        "alt_names": _str_list(data.get("alt_names")),
        "description": data.get("description"),
        "attribution": (
            [str(a) for a in attribution] if isinstance(attribution, list) else attribution
        ),
        "updated": data.get("updated"),
        "urls": _str_list(data.get("urls")),
        "notes": data.get("notes"),
        "uuid": data.get("uuid"),
        "library_entries": _str_list(data.get("library_entries")),
        "sources": _str_list(data.get("sources")),
        "url": _family_url(origin, ident),
    }


def parse_actor(payload: Any, *, ident: str, origin: str) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    syn = data.get("synonyms") or data.get("alt_names")
    families = data.get("families")
    meta = data.get("meta")
    return {
        "provider": "malpedia",
        "operation": "actor",
        "id": ident,
        "common_name": data.get("value") or data.get("common_name") or ident,
        "synonyms": _str_list(syn),
        "description": data.get("description"),
        "updated": data.get("updated"),
        "uuid": data.get("uuid"),
        "families": families if isinstance(families, dict) else {},
        "meta": meta if isinstance(meta, dict) else {},
        "url": _actor_url(origin, ident),
    }


def parse_yara(payload: Any, *, family: str | None = None, operation: str = "yara") -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    data = payload if isinstance(payload, dict) else {}
    for tlp, files in data.items():
        if not isinstance(files, dict):
            continue
        for filename, source in files.items():
            rules.append(
                {
                    "tlp": str(tlp),
                    "filename": str(filename),
                    "source": str(source) if source is not None else "",
                }
            )
    record: dict[str, Any] = {
        "provider": "malpedia",
        "operation": operation,
        "rules": rules,
    }
    if family is not None:
        record["family"] = family
    return record


def parse_samples(payload: Any, *, family: str | None) -> dict[str, Any]:
    items = payload if isinstance(payload, list) else []
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sha256 = item.get("sha256") or item.get("sha2") or item.get("hash")
        results.append(
            {
                "sha256": sha256,
                "md5": item.get("md5"),
                "sha1": item.get("sha1"),
                "status": item.get("status") or item.get("packed"),
                "version": item.get("version"),
                "family": item.get("family") or family,
            }
        )
    return {
        "provider": "malpedia",
        "operation": "samples",
        "family": family,
        "total": len(results),
        "results": results,
    }


def search(
    query: str,
    *,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    needle = (query or "").strip()
    families = _find_hits(
        _json(
            f"/api/find/family/{_segment(needle)}",
            origin=origin,
            token=token,
            transport=transport,
            timeout=timeout,
        )
    )
    actors = _find_hits(
        _json(
            f"/api/find/actor/{_segment(needle)}",
            origin=origin,
            token=token,
            transport=transport,
            timeout=timeout,
        )
    )
    for hit in families:
        hit["url"] = _family_url(origin, hit["name"])
    for hit in actors:
        hit["url"] = _actor_url(origin, hit["name"])
    return {
        "provider": "malpedia",
        "operation": "search",
        "query": needle,
        "families": families,
        "actors": actors,
    }


def family(
    ident: str,
    *,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    family_id = (ident or "").strip()
    payload = _json(
        f"/api/get/family/{_segment(family_id)}",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    return parse_family(payload, ident=family_id, origin=origin)


def actor(
    ident: str,
    *,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    actor_id = (ident or "").strip()
    payload = _json(
        f"/api/get/actor/{_segment(actor_id)}",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    return parse_actor(payload, ident=actor_id, origin=origin)


def families(
    *,
    limit: int | None = None,
    full: bool = False,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    path = "/api/get/families" if full else "/api/list/families"
    request, headers, body = _fetch(
        path, origin=origin, token=token, transport=transport, timeout=timeout
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="families",
            output=output,
            filename="malpedia_families.json",
            extra={"full": full},
        )
    payload = _loads(body)
    if full:
        data = payload if isinstance(payload, dict) else {}
        total = len(data)
        if limit is not None:
            keys = list(data.keys())[: max(0, int(limit))]
            data = {key: data[key] for key in keys}
        return {
            "provider": "malpedia",
            "operation": "families",
            "full": True,
            "total": total,
            "results": data,
        }
    ids = [str(item) for item in payload] if isinstance(payload, list) else []
    total = len(ids)
    if limit is not None:
        ids = ids[: max(0, int(limit))]
    return {
        "provider": "malpedia",
        "operation": "families",
        "full": False,
        "total": total,
        "results": ids,
    }


def actors(
    *,
    limit: int | None = None,
    full: bool = False,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    path = "/api/get/actors" if full else "/api/list/actors"
    request, headers, body = _fetch(
        path, origin=origin, token=token, transport=transport, timeout=timeout
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="actors",
            output=output,
            filename="malpedia_actors.json",
            extra={"full": full},
        )
    payload = _loads(body)
    if full:
        data = payload if isinstance(payload, dict) else {}
        total = len(data)
        if limit is not None:
            keys = list(data.keys())[: max(0, int(limit))]
            data = {key: data[key] for key in keys}
        return {
            "provider": "malpedia",
            "operation": "actors",
            "full": True,
            "total": total,
            "results": data,
        }
    ids = [str(item) for item in payload] if isinstance(payload, list) else []
    total = len(ids)
    if limit is not None:
        ids = ids[: max(0, int(limit))]
    return {
        "provider": "malpedia",
        "operation": "actors",
        "full": False,
        "total": total,
        "results": ids,
    }


def yara(
    ident: str,
    *,
    as_zip: bool = False,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    family_id = (ident or "").strip()
    if as_zip:
        request, headers, body = _fetch(
            f"/api/get/yara/{_segment(family_id)}/zip",
            origin=origin,
            token=token,
            transport=transport,
            timeout=timeout,
            accept="application/zip, */*",
        )
        return _artifact(
            request,
            headers,
            body,
            operation="yara",
            output=output,
            filename=f"{family_id}.zip",
            extra={"family": family_id, "format": "zip"},
        )
    payload = _json(
        f"/api/get/yara/{_segment(family_id)}",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    return parse_yara(payload, family=family_id)


def yara_list(
    *,
    family: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    payload = _json(
        "/api/list/yara",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    data = payload if isinstance(payload, dict) else {}
    family_id = (family or "").strip() or None
    if family_id:
        data = {family_id: data.get(family_id, [])}
    results: dict[str, Any] = {}
    total_rules = 0
    for name, rules in data.items():
        items = rules if isinstance(rules, list) else []
        total_rules += len(items)
        results[str(name)] = items
    return {
        "provider": "malpedia",
        "operation": "yara-list",
        "family": family_id,
        "total_families": len(results),
        "total_rules": total_rules,
        "results": results,
    }


def yara_dump(
    *,
    tlp: str | None = None,
    auto: bool = False,
    as_zip: bool = False,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    if auto == bool(tlp):
        raise ProviderHttpError("malpedia", 400, "pass exactly one of tlp or auto")
    if auto:
        path = "/api/get/yara/auto/zip" if as_zip else "/api/get/yara/auto/raw"
        default = "malpedia_auto_yar.zip" if as_zip else "malpedia_auto.yar"
        extra = {"bundle": "auto", "format": "zip" if as_zip else "yara"}
    else:
        tlp_id = normalize_tlp(str(tlp))
        path = f"/api/get/yara/{tlp_id}/zip" if as_zip else f"/api/get/yara/{tlp_id}/raw"
        default = f"malpedia_{tlp_id}.zip" if as_zip else f"malpedia_{tlp_id}.yar"
        extra = {"tlp": tlp_id, "format": "zip" if as_zip else "yara"}
    accept = "application/zip, */*" if as_zip else "application/yara, */*"
    request, headers, body = _fetch(
        path,
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
        accept=accept,
    )
    return _artifact(
        request,
        headers,
        body,
        operation="yara-dump",
        output=output,
        filename=default,
        extra=extra,
    )


def yara_after(
    date: str,
    *,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    day = (date or "").strip()
    if not _DATE_RE.match(day):
        raise ProviderHttpError("malpedia", 400, "date must be YYYY-MM-DD")
    request, headers, body = _fetch(
        f"/api/get/yara/after/{_segment(day)}",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="yara-after",
            output=output,
            filename=f"malpedia_yara_after_{day}.json",
            extra={"date": day},
        )
    payload = _loads(body)
    record = parse_yara(payload, operation="yara-after")
    record["date"] = day
    return record


def bib(
    *,
    family: str | None = None,
    actor: str | None = None,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    family_id = (family or "").strip() or None
    actor_id = (actor or "").strip() or None
    if family_id and actor_id:
        raise ProviderHttpError("malpedia", 400, "pass family or actor, not both")
    if family_id:
        path = f"/api/get/bib/family/{_segment(family_id)}"
        default = f"{family_id}.bib"
    elif actor_id:
        path = f"/api/get/bib/actor/{_segment(actor_id)}"
        default = f"{actor_id}.bib"
    else:
        path = "/api/get/bib"
        default = "malpedia.bib"
    request, headers, body = _fetch(
        path,
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
        accept="text/plain, */*",
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="bib",
            output=output,
            filename=default,
            extra={"family": family_id, "actor": actor_id},
        )
    text = body.decode("utf-8", errors="replace")
    return {
        "provider": "malpedia",
        "operation": "bib",
        "family": family_id,
        "actor": actor_id,
        "bibtex": text,
        "entries": parse_bibtex(text),
    }


def misp(
    *,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request, headers, body = _fetch(
        "/api/get/misp",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="misp",
            output=output,
            filename="malpedia_misp.json",
        )
    payload = _loads(body)
    return {
        "provider": "malpedia",
        "operation": "misp",
        "galaxy": payload if isinstance(payload, dict) else {"raw": payload},
    }


def references(
    *,
    url: str | None = None,
    output: str | None = None,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    request, headers, body = _fetch(
        "/api/get/references",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    if output:
        return _artifact(
            request,
            headers,
            body,
            operation="references",
            output=output,
            filename="malpedia_references.json",
        )
    payload = _loads(body)
    blob = payload if isinstance(payload, dict) else {}
    refs = blob.get("references") if isinstance(blob.get("references"), dict) else {}
    needle = (url or "").strip() or None
    if needle:
        refs = {needle: refs.get(needle, [])}
    return {
        "provider": "malpedia",
        "operation": "references",
        "malpedia_version": blob.get("malpedia_version"),
        "url": needle,
        "total": len(refs),
        "results": refs,
    }


def version(
    *,
    token: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    payload = _json(
        "/api/get/version",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    data = payload if isinstance(payload, dict) else {}
    return {
        "provider": "malpedia",
        "operation": "version",
        "version": data.get("version"),
        "date": data.get("date"),
    }


# Sample list/info/zip need Authorization: apitoken. Not wired in the CLI until
# we have a Malpedia invite.
def samples(
    ident: str | None = None,
    *,
    token: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    family_id = (ident or "").strip() or None
    path = (
        f"/api/list/samples/{_segment(family_id)}"
        if family_id
        else "/api/list/samples"
    )
    payload = _json(
        path, origin=origin, token=token, transport=transport, timeout=timeout
    )
    return parse_samples(payload, family=family_id)


def sample(
    target: str,
    *,
    token: str,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    digest = (target or "").strip()
    if not _HASH_RE.match(digest):
        raise ProviderHttpError(
            "malpedia", 400, "sample hash must be MD5 (32 hex) or SHA-256 (64 hex)"
        )
    payload = _json(
        f"/api/get/sample/{_segment(digest)}/info",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
    )
    data = payload if isinstance(payload, dict) else {"raw": payload}
    return {
        "provider": "malpedia",
        "operation": "sample",
        "hash": digest,
        "info": data,
    }


def download(
    target: str,
    *,
    token: str,
    output: str | None = None,
    origin: str = DEFAULT_ORIGIN,
    transport: Transport | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    digest = (target or "").strip()
    if not _HASH_RE.match(digest):
        raise ProviderHttpError(
            "malpedia", 400, "sample hash must be MD5 (32 hex) or SHA-256 (64 hex)"
        )
    request, headers, body = _fetch(
        f"/api/get/sample/{_segment(digest)}/zip",
        origin=origin,
        token=token,
        transport=transport,
        timeout=timeout,
        accept="application/zip, */*",
    )
    return _artifact(
        request,
        headers,
        body,
        operation="download",
        output=output,
        filename=f"{digest}.zip",
        extra={"hash": digest},
    )
