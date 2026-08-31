"""Telegram user MTProto via Telethon. Not Bot API.

Needs TELEGRAM_API_ID, TELEGRAM_API_HASH, and a saved user session
(TELEGRAM_SESSION and/or ~/.config/research-cli/telegram.session). Login is
once; later commands reuse the file until Telegram revokes the device.
Does not join groups or channels. Public post search is TGStat
(`research-cli tgstat search`); this client is login, discover, history,
resolve, get, and download.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from research_cli import __version__
from research_cli.errors import MissingKeyError, ProviderHttpError
from research_cli.keys import upsert_env_values

SESSION_EXPIRED = (
    "telegram session expired or revoked; run research-cli telegram login again"
)
_TME_HOST = r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog|ttttt\.me)/"
_INVITE_RE = re.compile(
    _TME_HOST + r"(?:joinchat/|\+)([\w-]{8,})(?:/(\d+))?", re.I
)
_INTERNAL_RE = re.compile(_TME_HOST + r"c/(\d+)(?:/(\d+))?", re.I)
_MSG_RE = re.compile(
    _TME_HOST + r"(?:s/)?(?!joinchat(?:/|$)|c/)([A-Za-z0-9_]+)/(\d+)", re.I
)
_USER_RE = re.compile(
    _TME_HOST + r"(?:s/)?(?!joinchat(?:/|$)|c/)([A-Za-z0-9_]+)/?$", re.I
)
FILE_MEDIA_TYPES = ("document", "photo", "video")
_AT_RE = re.compile(r"^@?([A-Za-z0-9_]{3,})$")
_TL: SimpleNamespace | None = None
ClientFactory = Callable[..., Any]


def _telethon() -> SimpleNamespace:
    global _TL
    if _TL is not None:
        return _TL
    try:
        from telethon import TelegramClient
        from telethon import errors
        from telethon.sessions import SQLiteSession, StringSession
        from telethon.tl.functions.contacts import ResolveUsernameRequest
        from telethon.tl.functions.contacts import SearchRequest as ContactsSearchRequest
        from telethon.tl.functions.messages import (
            CheckChatInviteRequest,
            GetHistoryRequest,
            SearchRequest,
        )
        from telethon.tl.types import InputMessagesFilterEmpty
    except ImportError as exc:
        raise ProviderHttpError(
            "telegram",
            0,
            "telethon is not installed; pip install -e .",
        ) from exc
    _TL = SimpleNamespace(
        TelegramClient=TelegramClient,
        StringSession=StringSession,
        SQLiteSession=SQLiteSession,
        errors=errors,
        SearchRequest=SearchRequest,
        GetHistoryRequest=GetHistoryRequest,
        CheckChatInviteRequest=CheckChatInviteRequest,
        ResolveUsernameRequest=ResolveUsernameRequest,
        ContactsSearchRequest=ContactsSearchRequest,
        InputMessagesFilterEmpty=InputMessagesFilterEmpty,
    )
    return _TL


def parse_target(value: str) -> dict[str, Any]:
    raw = (value or "").strip()
    if not raw:
        raise ProviderHttpError("telegram", 0, "empty telegram target")
    invite = _INVITE_RE.search(raw)
    if invite:
        out = {"kind": "invite", "hash": invite.group(1), "raw": raw}
        if invite.group(2):
            out["message_id"] = int(invite.group(2))
        return out
    internal = _INTERNAL_RE.search(raw)
    if internal:
        msg = internal.group(2)
        out: dict[str, Any] = {
            "kind": "internal",
            "channel_id": int(internal.group(1)),
            "raw": raw,
        }
        if msg:
            out["message_id"] = int(msg)
        return out
    msg_m = _MSG_RE.search(raw)
    if msg_m:
        return {
            "kind": "message",
            "username": msg_m.group(1),
            "message_id": int(msg_m.group(2)),
            "raw": raw,
        }
    user_m = _USER_RE.search(raw)
    if user_m:
        return {"kind": "username", "username": user_m.group(1), "raw": raw}
    at = _AT_RE.match(raw)
    if at:
        return {"kind": "username", "username": at.group(1), "raw": raw}
    if raw.lstrip("-").isdigit():
        return {"kind": "id", "id": int(raw), "raw": raw}
    raise ProviderHttpError("telegram", 0, f"unrecognized telegram target: {raw}")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(value)


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _chat_url(username: str | None, channel_id: int | None, msg_id: int | None) -> str | None:
    if username:
        base = f"https://t.me/{username}"
        return f"{base}/{msg_id}" if msg_id else base
    if channel_id:
        base = f"https://t.me/c/{channel_id}"
        return f"{base}/{msg_id}" if msg_id else base
    return None


def _peer_kind_id(peer: Any) -> tuple[str | None, int | None]:
    if peer is None:
        return None, None
    channel_id = getattr(peer, "channel_id", None)
    if channel_id is not None:
        return "channel", int(channel_id)
    chat_id = getattr(peer, "chat_id", None)
    if chat_id is not None:
        return "group", int(chat_id)
    user_id = getattr(peer, "user_id", None)
    if user_id is not None:
        return "user", int(user_id)
    ident = getattr(peer, "id", None)
    if ident is not None:
        if getattr(peer, "broadcast", False) or getattr(peer, "megagroup", False):
            kind = "channel" if getattr(peer, "broadcast", False) else "group"
            return kind, int(ident)
        if getattr(peer, "bot", False) or getattr(peer, "first_name", None) is not None:
            return "user", int(ident)
        return "group", int(ident)
    return None, None


def _index_peers(users: Any, chats: Any) -> dict[tuple[str, int], Any]:
    indexed: dict[tuple[str, int], Any] = {}
    for item in list(users or []) + list(chats or []):
        kind, ident = _peer_kind_id(item)
        if kind and ident is not None:
            indexed[(kind, ident)] = item
    return indexed


def serialize_user(user: Any) -> dict[str, Any]:
    ident = _int(getattr(user, "id", None))
    username = getattr(user, "username", None)
    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""
    name = " ".join(part for part in (first, last) if part).strip() or None
    payload: dict[str, Any] = {"id": ident, "username": username, "name": name}
    if getattr(user, "premium", False):
        payload["premium"] = True
    if getattr(user, "bot", False):
        payload["bot"] = True
    if getattr(user, "phone", None):
        payload["phone"] = user.phone
    payload["url"] = _chat_url(username, None, None)
    return {key: value for key, value in payload.items() if value is not None}


def serialize_chat(chat: Any) -> dict[str, Any]:
    kind, ident = _peer_kind_id(chat)
    username = getattr(chat, "username", None)
    title = getattr(chat, "title", None)
    payload: dict[str, Any] = {
        "id": ident,
        "type": kind,
        "username": username,
        "title": title or getattr(chat, "first_name", None),
        "url": _chat_url(username, ident if kind == "channel" else None, None),
    }
    count = _int(getattr(chat, "participants_count", None))
    if count is not None:
        payload["participants"] = count
    if getattr(chat, "broadcast", False):
        payload["broadcast"] = True
    if getattr(chat, "megagroup", False):
        payload["megagroup"] = True
    return {key: value for key, value in payload.items() if value is not None}


def serialize_media(media: Any) -> dict[str, Any] | None:
    if media is None or type(media).__name__ == "MessageMediaEmpty":
        return None
    doc = getattr(media, "document", None)
    if doc is not None:
        name = None
        kind = "document"
        for attr in getattr(doc, "attributes", None) or []:
            filename = getattr(attr, "file_name", None)
            if filename:
                name = filename
            attr_name = type(attr).__name__
            if "Video" in attr_name:
                kind = "video"
        payload = {
            "type": kind,
            "id": _int(getattr(doc, "id", None)),
            "name": name,
            "mime": getattr(doc, "mime_type", None),
            "size": _int(getattr(doc, "size", None)),
        }
        return {key: value for key, value in payload.items() if value is not None}
    photo = getattr(media, "photo", None)
    if photo is not None:
        payload = {
            "type": "photo",
            "id": _int(getattr(photo, "id", None)),
            "mime": "image/jpeg",
        }
        size = _int(getattr(photo, "size", None))
        if size is None:
            sizes = getattr(photo, "sizes", None) or []
            if sizes:
                size = _int(getattr(sizes[-1], "size", None))
        if size is not None:
            payload["size"] = size
        return payload
    webpage = getattr(media, "webpage", None)
    if webpage is not None:
        payload = {
            "type": "web_page",
            "url": getattr(webpage, "url", None),
            "title": getattr(webpage, "title", None),
        }
        return {key: value for key, value in payload.items() if value is not None}
    return {"type": type(media).__name__}


def media_is_file(media: Any) -> bool:
    if isinstance(media, dict):
        return media.get("type") in FILE_MEDIA_TYPES
    classified = serialize_media(media) if media is not None else None
    return bool(classified) and classified.get("type") in FILE_MEDIA_TYPES


def serialize_message(msg: Any, peers: Mapping[tuple[str, int], Any] | None = None) -> dict[str, Any] | None:
    ident = _int(getattr(msg, "id", None))
    if ident is None or type(msg).__name__ == "MessageEmpty":
        return None
    kind, peer_id = _peer_kind_id(getattr(msg, "peer_id", None))
    chat_obj = (peers or {}).get((kind or "", peer_id or 0))
    chat = serialize_chat(chat_obj) if chat_obj is not None else {
        "id": peer_id,
        "type": kind,
    }
    username = chat.get("username") if isinstance(chat, dict) else None
    channel_id = peer_id if kind == "channel" else None
    from_peer = getattr(msg, "from_id", None)
    from_kind, from_id = _peer_kind_id(from_peer)
    from_obj = (peers or {}).get((from_kind or "", from_id or 0))
    sender = serialize_user(from_obj) if from_obj is not None else (
        {"id": from_id} if from_id is not None else None
    )
    reply = getattr(msg, "reply_to", None)
    payload: dict[str, Any] = {
        "id": ident,
        "date": _iso(getattr(msg, "date", None)),
        "text": getattr(msg, "message", None) or "",
        "chat": chat,
        "from": sender,
        "url": _chat_url(username, channel_id, ident),
        "views": _int(getattr(msg, "views", None)),
        "forwards": _int(getattr(msg, "forwards", None)),
        "grouped_id": _int(getattr(msg, "grouped_id", None)),
        "reply_to": _int(getattr(reply, "reply_to_msg_id", None) if reply is not None else None),
        "media": serialize_media(getattr(msg, "media", None)),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", {}, [])}


def serialize_messages(result: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    peers = _index_peers(getattr(result, "users", None), getattr(result, "chats", None))
    messages: list[dict[str, Any]] = []
    for item in getattr(result, "messages", None) or []:
        parsed = serialize_message(item, peers)
        if parsed:
            messages.append(parsed)
    extra: dict[str, Any] = {}
    next_rate = _int(getattr(result, "next_rate", None))
    if next_rate is not None:
        extra["offset_rate"] = next_rate
    if messages:
        extra["offset_id"] = messages[-1]["id"]
        extra["offset_peer"] = (messages[-1].get("chat") or {}).get("username") or (
            messages[-1].get("chat") or {}
        ).get("id")
    count = _int(getattr(result, "count", None))
    if count is not None:
        extra["count"] = count
    flood = getattr(result, "search_flood", None)
    if flood is not None:
        extra["flood"] = serialize_flood(flood)
    return messages, extra


def serialize_flood(flood: Any) -> dict[str, Any]:
    payload = {
        "query_is_free": bool(getattr(flood, "query_is_free", False)),
        "total_daily": _int(getattr(flood, "total_daily", None)),
        "remains": _int(getattr(flood, "remains", None)),
        "wait_till": _iso(getattr(flood, "wait_till", None))
        if not isinstance(getattr(flood, "wait_till", None), int)
        else getattr(flood, "wait_till", None),
        "stars_amount": _int(getattr(flood, "stars_amount", None)),
    }
    return {key: value for key, value in payload.items() if value is not None}


def serialize_invite(invite: Any) -> dict[str, Any]:
    name = type(invite).__name__
    if name == "ChatInviteAlready":
        chat = serialize_chat(getattr(invite, "chat", None))
        return {"status": "already_member", "chat": chat}
    if name == "ChatInvitePeek":
        return {
            "status": "peek",
            "expires": _iso(getattr(invite, "expires", None))
            if not isinstance(getattr(invite, "expires", None), int)
            else getattr(invite, "expires", None),
            "chat": serialize_chat(getattr(invite, "chat", None)),
        }
    payload: dict[str, Any] = {
        "status": "preview",
        "title": getattr(invite, "title", None),
        "about": getattr(invite, "about", None),
        "participants": _int(getattr(invite, "participants_count", None)),
        "request_needed": bool(getattr(invite, "request_needed", False)),
        "channel": bool(getattr(invite, "channel", False)),
        "broadcast": bool(getattr(invite, "broadcast", False)),
        "public": bool(getattr(invite, "public", False)),
        "megagroup": bool(getattr(invite, "megagroup", False)),
    }
    return {key: value for key, value in payload.items() if value not in (None, False)}


def mapped_error_body(exc: BaseException) -> str | None:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    blob = f"{name} {text}"
    if "expired" in blob or "invite_hash_expired" in blob or "invite_hash_invalid" in blob:
        return "expired invite"
    if "user_not_participant" in blob or "not a member" in blob:
        return "not a member"
    if "no downloadable media" in blob or "has no downloadable media" in blob:
        return "no media"
    if "no media" in blob and "downloadable" not in blob:
        return "no media"
    if (
        "message_id_invalid" in blob
        or "messageempty" in blob
        or "message not found" in blob
        or " is deleted" in blob
    ):
        return "deleted"
    return None


def _raise_rpc(exc: BaseException) -> None:
    name = type(exc).__name__
    if name in {
        "AuthKeyUnregisteredError",
        "SessionExpiredError",
        "SessionRevokedError",
        "AuthKeyDuplicatedError",
        "AuthKeyInvalidError",
    }:
        raise MissingKeyError(
            "telegram",
            ("TELEGRAM_SESSION",),
            detail=SESSION_EXPIRED,
        ) from exc
    seconds = getattr(exc, "seconds", None)
    if seconds is not None and "Flood" in name:
        raise ProviderHttpError(
            "telegram", 420, f"FLOOD_WAIT retry after {int(seconds)}s"
        ) from exc
    mapped = mapped_error_body(exc)
    code = getattr(exc, "code", 0) or 0
    raise ProviderHttpError(
        "telegram", int(code), mapped or str(exc)
    ) from exc


def _run(coro: Any) -> Any:
    if os.name == "nt":
        policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop_policy(policy())
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise ProviderHttpError(
        "telegram", 0, "cannot run telegram client inside a running event loop"
    )


@contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _sqlite_to_string(path: Path) -> str | None:
    tl = _telethon()
    sql = None
    try:
        sql = tl.SQLiteSession(str(path))
        conn = getattr(sql, "_conn", None)
        if conn is not None:
            conn.execute("PRAGMA busy_timeout=30000")
        dumped = tl.StringSession.save(sql)
        return dumped or None
    except Exception:
        return None
    finally:
        close = getattr(sql, "close", None) if sql is not None else None
        if close is not None:
            close()


def _string_to_sqlite(string: str, path: Path) -> None:
    tl = _telethon()
    src = tl.StringSession(string)
    if not getattr(src, "auth_key", None):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(path.with_name(path.name + ".lock")):
        sql = tl.SQLiteSession(str(path))
        try:
            conn = getattr(sql, "_conn", None)
            if conn is not None:
                conn.execute("PRAGMA busy_timeout=30000")
            sql.set_dc(src.dc_id, src.server_address, src.port)
            sql.auth_key = src.auth_key
            sql.save()
        finally:
            close = getattr(sql, "close", None)
            if close is not None:
                close()
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _load_string_session(session: str, session_file: str | Path | None) -> Any:
    tl = _telethon()
    if session_file:
        path = Path(session_file)
        if path.is_file() and path.stat().st_size > 0:
            dumped = _sqlite_to_string(path)
            if dumped:
                return tl.StringSession(dumped)
    return tl.StringSession(session or "")


def default_client(
    session: str,
    api_id: int,
    api_hash: str,
    timeout: float,
    session_file: str | Path | None = None,
) -> Any:
    tl = _telethon()
    storage = _load_string_session(session, session_file)
    return tl.TelegramClient(
        storage,
        api_id,
        api_hash,
        timeout=int(timeout) if timeout else 10,
        flood_sleep_threshold=0,
        receive_updates=False,
        device_model="research-cli",
        system_version=f"{platform.system()} {platform.release()}".strip(),
        app_version=__version__,
        lang_code="en",
        system_lang_code="en",
    )


def _persist_session(
    client: Any,
    env_path: Path | None,
    session_file: str | Path | None,
) -> None:
    string = _session_string(client)
    if env_path and string:
        upsert_env_values(Path(env_path), {"TELEGRAM_SESSION": string})
    if session_file and string:
        try:
            _string_to_sqlite(string, Path(session_file))
        except Exception:
            return


async def _connect(
    *,
    session: str,
    api_id: int,
    api_hash: str,
    timeout: float,
    client_factory: ClientFactory | None,
    require_auth: bool,
    session_file: str | Path | None = None,
) -> Any:
    if client_factory is not None:
        client = client_factory(session, api_id, api_hash, timeout)
    else:
        client = default_client(
            session, api_id, api_hash, timeout, session_file=session_file
        )
    connect = getattr(client, "connect", None)
    if connect is not None:
        result = connect()
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            await result
    if require_auth:
        check = getattr(client, "is_user_authorized", None)
        authorized = True
        if check is not None:
            authorized = check()
            if asyncio.iscoroutine(authorized) or asyncio.isfuture(authorized):
                authorized = await authorized
        if not authorized:
            raise MissingKeyError(
                "telegram",
                ("TELEGRAM_SESSION",),
                detail=SESSION_EXPIRED,
            )
    return client


async def _disconnect(
    client: Any,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> None:
    disconnect = getattr(client, "disconnect", None)
    if disconnect is not None:
        result = disconnect()
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            await result
    _persist_session(client, env_path, session_file)


async def _call(client: Any, request: Any) -> Any:
    try:
        return await client(request)
    except MissingKeyError:
        raise
    except ProviderHttpError:
        raise
    except Exception as exc:
        _raise_rpc(exc)


def _session_string(client: Any) -> str | None:
    session = getattr(client, "session", None)
    save = getattr(session, "save", None)
    if save is None:
        return None
    value = save()
    return str(value) if value else None


def _dest_path(output: str | None, filename: str) -> Path:
    if output:
        dest = Path(output).expanduser()
        if dest.exists() and dest.is_dir():
            return dest / filename
        return dest
    return Path.cwd() / filename


def _media_filename(msg: Any, message_id: int) -> str:
    media = serialize_media(getattr(msg, "media", None)) or {}
    name = media.get("name")
    if isinstance(name, str) and name.strip():
        return Path(name).name
    mime = str(media.get("mime") or "")
    suffix = {
        "photo": ".jpg",
        "application/zip": ".zip",
        "application/pdf": ".pdf",
        "video/mp4": ".mp4",
    }.get(media.get("type") if media.get("type") != "document" else mime, "")
    if mime.startswith("image/"):
        suffix = ".jpg"
    return f"telegram-{message_id}{suffix}"


def _write_login_env(
    env_path: Path | None,
    *,
    api_id: int,
    api_hash: str,
    session: str | None,
    phone: str | None = None,
    phone_code_hash: str | None = None,
    drop_pending: bool = False,
) -> str | None:
    if env_path is None:
        return None
    values = {
        "TELEGRAM_API_ID": str(api_id),
        "TELEGRAM_API_HASH": api_hash,
    }
    if session:
        values["TELEGRAM_SESSION"] = session
    drop: tuple[str, ...] = ()
    if drop_pending:
        drop = ("TELEGRAM_PHONE", "TELEGRAM_PHONE_CODE_HASH")
    else:
        if phone:
            values["TELEGRAM_PHONE"] = phone
        if phone_code_hash:
            values["TELEGRAM_PHONE_CODE_HASH"] = phone_code_hash
    upsert_env_values(env_path, values, drop=drop)
    return str(env_path)


def login(
    *,
    phone: str,
    api_id: int,
    api_hash: str,
    session: str = "",
    code: str | None = None,
    phone_code_hash: str | None = None,
    password: str | None = None,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    number = (phone or "").strip()
    if not number:
        raise ProviderHttpError(
            "telegram",
            0,
            "telegram login needs --phone the first time (then --code)",
        )

    async def _go() -> dict[str, Any]:
        # A saved authorized session is bound to one DC. Logging in a
        # different phone (PHONE_MIGRATE) must start empty or Telegram
        # refuses to switch DCs. Completing 2FA reuses the pending session.
        fresh = not (code or "").strip() and not (password or "").strip()
        client = await _connect(
            session="" if fresh else (session or ""),
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=False,
            session_file=None if fresh else session_file,
        )
        tl = _telethon()
        try:
            if not code and not (password or "").strip():
                try:
                    sent = await client.send_code_request(number)
                except Exception as exc:
                    new_dc = getattr(exc, "new_dc", None)
                    switch = getattr(client, "_switch_dc", None)
                    if new_dc and switch is not None and "Migrate" in type(exc).__name__:
                        result = switch(new_dc)
                        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                            await result
                        sent = await client.send_code_request(number)
                    else:
                        _raise_rpc(exc)
                session_s = _session_string(client)
                hash_s = getattr(sent, "phone_code_hash", None)
                written = _write_login_env(
                    env_path,
                    api_id=api_id,
                    api_hash=api_hash,
                    session=session_s,
                    phone=number,
                    phone_code_hash=str(hash_s) if hash_s else None,
                )
                payload = {
                    "provider": "telegram",
                    "operation": "login",
                    "status": "code_sent",
                    "phone": number,
                    "hint": "Telegram sent a login code. Rerun: research-cli telegram login --code CODE",
                }
                if written:
                    payload["env_file"] = written
                else:
                    payload["phone_code_hash"] = hash_s
                    payload["session"] = session_s
                return payload
            if (password or "").strip() and not (code or "").strip():
                try:
                    me = await client.sign_in(password=password.strip())
                except Exception as exc:
                    _raise_rpc(exc)
            else:
                try:
                    me = await client.sign_in(
                        phone=number,
                        code=code.strip(),
                        phone_code_hash=(phone_code_hash or "").strip() or None,
                    )
                except tl.errors.SessionPasswordNeededError:
                    if not (password or "").strip():
                        session_s = _session_string(client)
                        written = _write_login_env(
                            env_path,
                            api_id=api_id,
                            api_hash=api_hash,
                            session=session_s,
                            phone=number,
                            phone_code_hash=(phone_code_hash or "").strip() or None,
                        )
                        payload = {
                            "provider": "telegram",
                            "operation": "login",
                            "status": "password_needed",
                            "phone": number,
                            "hint": "2FA on. Rerun: research-cli telegram login --password ...",
                        }
                        if written:
                            payload["env_file"] = written
                        else:
                            payload["session"] = session_s
                        return payload
                    me = await client.sign_in(password=password.strip())
                except Exception as exc:
                    if type(exc).__name__ == "SessionPasswordNeededError":
                        if not (password or "").strip():
                            session_s = _session_string(client)
                            written = _write_login_env(
                                env_path,
                                api_id=api_id,
                                api_hash=api_hash,
                                session=session_s,
                                phone=number,
                                phone_code_hash=(phone_code_hash or "").strip() or None,
                            )
                            payload = {
                                "provider": "telegram",
                                "operation": "login",
                                "status": "password_needed",
                                "phone": number,
                                "hint": "2FA on. Rerun: research-cli telegram login --password ...",
                            }
                            if written:
                                payload["env_file"] = written
                            else:
                                payload["session"] = session_s
                            return payload
                        me = await client.sign_in(password=password.strip())
                    else:
                        _raise_rpc(exc)
            session_s = _session_string(client)
            written = _write_login_env(
                env_path,
                api_id=api_id,
                api_hash=api_hash,
                session=session_s,
                drop_pending=True,
            )
            payload = {
                "provider": "telegram",
                "operation": "login",
                "status": "authorized",
                "user": serialize_user(me),
                "hint": "session saved; later telegram commands do not need --phone or --code",
            }
            if written:
                payload["env_file"] = written
            else:
                payload["session"] = session_s
            return payload
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


def me(
    *,
    api_id: int,
    api_hash: str,
    session: str,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            user = await client.get_me()
            return {
                "provider": "telegram",
                "operation": "me",
                "user": serialize_user(user),
            }
        except MissingKeyError:
            raise
        except ProviderHttpError:
            raise
        except Exception as exc:
            _raise_rpc(exc)
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


def discover(
    query: str,
    *,
    api_id: int,
    api_hash: str,
    session: str,
    limit: int = 20,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise ProviderHttpError("telegram", 0, "empty discover query")
    tl = _telethon()

    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            result = await _call(
                client,
                tl.ContactsSearchRequest(q=q, limit=max(1, min(limit, 50))),
            )
            users = [serialize_user(item) for item in getattr(result, "users", None) or []]
            chats = [serialize_chat(item) for item in getattr(result, "chats", None) or []]
            return {
                "provider": "telegram",
                "operation": "discover",
                "query": q,
                "users": users,
                "chats": chats,
            }
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


async def _input_peer(client: Any, target: dict[str, Any]) -> Any:
    tl = _telethon()
    if target["kind"] in {"username", "message"}:
        result = await _call(
            client, tl.ResolveUsernameRequest(username=target["username"])
        )
        peer = getattr(result, "peer", None)
        chats = list(getattr(result, "chats", None) or [])
        users = list(getattr(result, "users", None) or [])
        kind, ident = _peer_kind_id(peer)
        for item in chats + users:
            item_kind, item_id = _peer_kind_id(item)
            if item_kind == kind and item_id == ident:
                return item
        raise ProviderHttpError(
            "telegram", 0, f"could not resolve @{target['username']}"
        )
    if target["kind"] == "internal":
        getter = getattr(client, "get_input_entity", None)
        if getter is None:
            raise ProviderHttpError(
                "telegram",
                0,
                "internal t.me/c/ id needs a client entity cache; use a public @username",
            )
        try:
            entity = getter(target["channel_id"])
            if asyncio.iscoroutine(entity) or asyncio.isfuture(entity):
                entity = await entity
            return entity
        except Exception as exc:
            raise ProviderHttpError(
                "telegram",
                0,
                "unknown internal channel id; use a public @username "
                "(CLI does not join)",
            ) from exc
    if target["kind"] == "id":
        getter = getattr(client, "get_input_entity", None)
        if getter is None:
            raise ProviderHttpError("telegram", 0, "cannot resolve numeric id")
        entity = getter(target["id"])
        if asyncio.iscoroutine(entity) or asyncio.isfuture(entity):
            entity = await entity
        return entity
    if target["kind"] == "invite":
        invite = await _call(client, tl.CheckChatInviteRequest(hash=target["hash"]))
        if type(invite).__name__ != "ChatInviteAlready":
            raise ProviderHttpError("telegram", 0, "not a member")
        chat = getattr(invite, "chat", None)
        if chat is None:
            raise ProviderHttpError("telegram", 0, "invite has no chat")
        getter = getattr(client, "get_input_entity", None)
        if getter is not None:
            entity = getter(chat)
            if asyncio.iscoroutine(entity) or asyncio.isfuture(entity):
                entity = await entity
            return entity
        return chat
    raise ProviderHttpError(
        "telegram", 0, f"target {target['kind']} is not a chat; use resolve for invites"
    )


def history(
    target: str,
    *,
    api_id: int,
    api_hash: str,
    session: str,
    search_query: str | None = None,
    limit: int = 50,
    offset_id: int = 0,
    min_id: int = 0,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    parsed = parse_target(target)
    if parsed["kind"] == "invite":
        raise ProviderHttpError(
            "telegram",
            0,
            "invite links are resolve-only; CLI does not join",
        )
    q = (search_query or "").strip()
    tl = _telethon()
    start_id = offset_id or int(parsed.get("message_id") or 0)

    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            peer = await _input_peer(client, parsed)
            if q:
                result = await _call(
                    client,
                    tl.SearchRequest(
                        peer=peer,
                        q=q,
                        filter=tl.InputMessagesFilterEmpty(),
                        min_date=None,
                        max_date=None,
                        offset_id=start_id,
                        add_offset=0,
                        limit=max(1, min(limit, 100)),
                        max_id=0,
                        min_id=min_id or 0,
                        hash=0,
                    ),
                )
            else:
                result = await _call(
                    client,
                    tl.GetHistoryRequest(
                        peer=peer,
                        offset_id=start_id,
                        offset_date=None,
                        add_offset=0,
                        limit=max(1, min(limit, 100)),
                        max_id=0,
                        min_id=min_id or 0,
                        hash=0,
                    ),
                )
            messages, extra = serialize_messages(result)
            payload = {
                "provider": "telegram",
                "operation": "history",
                "target": parsed,
                "search": q or None,
                "results": messages,
            }
            payload.update(extra)
            return {key: value for key, value in payload.items() if value is not None}
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


def resolve(
    target: str,
    *,
    api_id: int,
    api_hash: str,
    session: str,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    parsed = parse_target(target)
    tl = _telethon()

    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            if parsed["kind"] == "invite":
                try:
                    invite = await _call(
                        client, tl.CheckChatInviteRequest(hash=parsed["hash"])
                    )
                except ProviderHttpError as exc:
                    if "expired invite" in str(exc):
                        return {
                            "provider": "telegram",
                            "operation": "resolve",
                            "target": parsed,
                            "invite": {"status": "expired"},
                        }
                    raise
                serialized = serialize_invite(invite)
                if serialized.get("request_needed"):
                    serialized["status"] = "request_needed"
                return {
                    "provider": "telegram",
                    "operation": "resolve",
                    "target": parsed,
                    "invite": serialized,
                }
            if parsed["kind"] in {"username", "message"}:
                result = await _call(
                    client, tl.ResolveUsernameRequest(username=parsed["username"])
                )
                chats = [serialize_chat(item) for item in getattr(result, "chats", None) or []]
                users = [serialize_user(item) for item in getattr(result, "users", None) or []]
                kind, ident = _peer_kind_id(getattr(result, "peer", None))
                return {
                    "provider": "telegram",
                    "operation": "resolve",
                    "target": parsed,
                    "peer": {"type": kind, "id": ident},
                    "chats": chats,
                    "users": users,
                }
            raise ProviderHttpError(
                "telegram",
                0,
                "resolve a @username, t.me/user, or t.me/+invite (CLI does not join)",
            )
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


def _message_ref(
    target: str, chat: str | None = None
) -> tuple[dict[str, Any], int]:
    parsed = parse_target(target)
    message_id = parsed.get("message_id")
    chat_target = chat
    if parsed["kind"] == "message":
        chat_target = parsed["username"]
    elif parsed["kind"] == "internal":
        chat_target = f"https://t.me/c/{parsed['channel_id']}"
        message_id = parsed.get("message_id") or message_id
    elif parsed["kind"] == "invite":
        chat_target = f"https://t.me/joinchat/{parsed['hash']}"
        message_id = parsed.get("message_id") or message_id
    elif parsed["kind"] == "id":
        message_id = parsed["id"]
    if not message_id:
        raise ProviderHttpError(
            "telegram",
            0,
            "needs a message id or https://t.me/user/id",
        )
    if not chat_target:
        raise ProviderHttpError(
            "telegram", 0, "bare message id needs --chat @username"
        )
    return parse_target(str(chat_target)), int(message_id)


def _stamp_known_chat(
    record: dict[str, Any] | None,
    parsed: dict[str, Any],
    message_id: int,
) -> dict[str, Any] | None:
    if not record:
        return record
    chat = dict(record.get("chat") or {})
    username = chat.get("username") or parsed.get("username")
    channel_id = parsed.get("channel_id") or (
        chat.get("id") if chat.get("type") == "channel" else None
    )
    if username:
        chat["username"] = username
        chat["url"] = _chat_url(str(username), None, None)
        record["url"] = _chat_url(str(username), None, message_id)
    elif channel_id:
        chat.setdefault("url", _chat_url(None, int(channel_id), None))
        record.setdefault("url", _chat_url(None, int(channel_id), message_id))
    record["chat"] = {key: value for key, value in chat.items() if value is not None}
    return record


def _peers_for(peer: Any, msg: Any) -> dict[tuple[str, int], Any]:
    indexed = _index_peers(
        getattr(msg, "users", None),
        list(getattr(msg, "chats", None) or []) + [peer],
    )
    kind, ident = _peer_kind_id(peer)
    if kind and ident is not None:
        indexed[(kind, ident)] = peer
    msg_kind, msg_id = _peer_kind_id(getattr(msg, "peer_id", None))
    if msg_kind and msg_id is not None and (msg_kind, msg_id) not in indexed:
        indexed[(msg_kind, msg_id)] = peer
    return indexed


async def _load_message(
    client: Any, chat_parsed: dict[str, Any], message_id: int
) -> tuple[Any, Any]:
    peer = await _input_peer(client, chat_parsed)
    getter = getattr(client, "get_messages")
    msg = getter(peer, ids=int(message_id))
    if asyncio.iscoroutine(msg) or asyncio.isfuture(msg):
        msg = await msg
    if isinstance(msg, list):
        msg = msg[0] if msg else None
    if msg is None or type(msg).__name__ == "MessageEmpty":
        raise ProviderHttpError("telegram", 0, "deleted")
    return peer, msg


def get(
    target: str,
    *,
    api_id: int,
    api_hash: str,
    session: str,
    chat: str | None = None,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    chat_parsed, message_id = _message_ref(target, chat)

    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            peer, msg = await _load_message(client, chat_parsed, message_id)
            record = _stamp_known_chat(
                serialize_message(msg, _peers_for(peer, msg)),
                chat_parsed,
                int(message_id),
            )
            media = (record or {}).get("media")
            return {
                "provider": "telegram",
                "operation": "get",
                "id": int(message_id),
                "has_media": media_is_file(media),
                "media": media,
                "message": record,
            }
        except MissingKeyError:
            raise
        except ProviderHttpError:
            raise
        except Exception as exc:
            _raise_rpc(exc)
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())


def download(
    target: str,
    *,
    api_id: int,
    api_hash: str,
    session: str,
    chat: str | None = None,
    output: str | None = None,
    timeout: float = 60.0,
    client_factory: ClientFactory | None = None,
    env_path: Path | None = None,
    session_file: str | Path | None = None,
) -> dict[str, Any]:
    chat_parsed, message_id = _message_ref(target, chat)

    async def _go() -> dict[str, Any]:
        client = await _connect(
            session=session,
            api_id=api_id,
            api_hash=api_hash,
            timeout=timeout,
            client_factory=client_factory,
            require_auth=True,
            session_file=session_file,
        )
        try:
            peer, msg = await _load_message(client, chat_parsed, message_id)
            media = serialize_media(getattr(msg, "media", None))
            if not media_is_file(media):
                raise ProviderHttpError("telegram", 0, "no media")
            filename = _media_filename(msg, int(message_id))
            dest = _dest_path(output, filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloader = getattr(client, "download_media")
            saved = downloader(msg, file=str(dest))
            if asyncio.iscoroutine(saved) or asyncio.isfuture(saved):
                saved = await saved
            path = Path(str(saved or dest)).expanduser()
            size = path.stat().st_size if path.is_file() else None
            record = _stamp_known_chat(
                serialize_message(msg, _peers_for(peer, msg)),
                chat_parsed,
                int(message_id),
            )
            return {
                "provider": "telegram",
                "operation": "download",
                "id": int(message_id),
                "path": str(path.resolve()) if path.exists() else str(dest.resolve()),
                "filename": path.name if path.exists() else filename,
                "size": size,
                "message": record,
            }
        except MissingKeyError:
            raise
        except ProviderHttpError:
            raise
        except Exception as exc:
            _raise_rpc(exc)
        finally:
            await _disconnect(client, env_path=env_path, session_file=session_file)

    return _run(_go())
