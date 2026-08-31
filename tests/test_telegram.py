from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.errors import MissingKeyError, ProviderHttpError  # noqa: E402
from research_cli.keys import (  # noqa: E402
    optional_telegram_session,
    parse_env_file,
    require_telegram_app,
    require_telegram_session,
)
from research_cli.providers import telegram  # noqa: E402


def _dt() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _channel() -> SimpleNamespace:
    return SimpleNamespace(
        id=99,
        username="rev",
        title="Rev",
        broadcast=True,
        megagroup=False,
        participants_count=10,
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        username="alice",
        first_name="Alice",
        last_name="",
        bot=False,
        phone=None,
    )


def _msg(**kwargs: object) -> SimpleNamespace:
    data = dict(
        id=11,
        date=_dt(),
        message="hello llvm",
        grouped_id=None,
        peer_id=SimpleNamespace(channel_id=99),
        from_id=SimpleNamespace(user_id=7),
        media=None,
        views=3,
        forwards=1,
        reply_to=None,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _messages_result(*messages: object, **extra: object) -> SimpleNamespace:
    return SimpleNamespace(
        messages=list(messages),
        chats=[_channel()],
        users=[_user()],
        next_rate=50,
        count=len(messages),
        **extra,
    )


class FakeClient:
    def __init__(self, **handlers: object) -> None:
        self.handlers = handlers
        self.calls: list[object] = []
        self.connects = 0
        self.authorized = bool(handlers.get("authorized", True))
        self.session = SimpleNamespace(save=lambda: "SESS")
        self.me = SimpleNamespace(
            id=1, username="me", first_name="Me", last_name="", bot=False, phone="1"
        )

    async def connect(self) -> None:
        self.connects += 1
        return None

    async def disconnect(self) -> None:
        return None

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_me(self) -> object:
        fn = self.handlers.get("get_me")
        if callable(fn):
            return fn()
        return self.me

    async def send_code_request(self, phone: str) -> object:
        self.calls.append(("send_code", phone))
        fn = self.handlers.get("send_code")
        if callable(fn):
            return fn(phone)
        return SimpleNamespace(phone_code_hash="HASH")

    async def sign_in(self, **kwargs: object) -> object:
        self.calls.append(("sign_in", kwargs))
        fn = self.handlers.get("sign_in")
        if callable(fn):
            return fn(kwargs)
        return self.me

    async def __call__(self, request: object) -> object:
        self.calls.append(request)
        name = type(request).__name__
        fn = self.handlers.get(name)
        if callable(fn):
            return fn(request)
        raise AssertionError(f"unexpected request {name}")

    async def get_input_entity(self, item: object) -> object:
        fn = self.handlers.get("get_input_entity")
        if callable(fn):
            return fn(item)
        return item

    async def get_messages(self, peer: object, ids: object = None) -> object:
        fn = self.handlers.get("get_messages")
        if callable(fn):
            return fn(peer, ids)
        raise AssertionError("get_messages")

    async def download_media(self, msg: object, file: str | None = None) -> str:
        fn = self.handlers.get("download_media")
        if callable(fn):
            return fn(msg, file)
        path = Path(file or "out.bin")
        path.write_bytes(b"data")
        return str(path)


def _factory(client: FakeClient):
    return lambda session, api_id, api_hash, timeout: client


class ParseTargetTests(unittest.TestCase):
    def test_username_invite_message_internal(self) -> None:
        self.assertEqual(telegram.parse_target("@durov")["username"], "durov")
        self.assertEqual(telegram.parse_target("https://t.me/durov")["kind"], "username")
        self.assertEqual(telegram.parse_target("https://t.me/s/durov")["username"], "durov")
        msg = telegram.parse_target("https://t.me/durov/12")
        self.assertEqual(msg, {"kind": "message", "username": "durov", "message_id": 12, "raw": "https://t.me/durov/12"})
        invite = telegram.parse_target("https://t.me/+AbCdefgh")
        self.assertEqual(invite["kind"], "invite")
        self.assertEqual(invite["hash"], "AbCdefgh")
        join = telegram.parse_target("https://t.me/joinchat/AbCdefgh")
        self.assertEqual(join["hash"], "AbCdefgh")
        self.assertNotIn("message_id", join)
        join_msg = telegram.parse_target("https://t.me/joinchat/AbCdefgh/99")
        self.assertEqual(join_msg["hash"], "AbCdefgh")
        self.assertEqual(join_msg["message_id"], 99)
        with self.assertRaises(ProviderHttpError):
            telegram.parse_target("https://t.me/joinchat/6")
        tttt = telegram.parse_target("https://ttttt.me/durov/12")
        self.assertEqual(tttt["kind"], "message")
        self.assertEqual(tttt["username"], "durov")
        internal = telegram.parse_target("https://t.me/c/123/45")
        self.assertEqual(internal["channel_id"], 123)
        self.assertEqual(internal["message_id"], 45)
        self.assertEqual(telegram.parse_target("99")["id"], 99)
        with self.assertRaises(ProviderHttpError):
            telegram.parse_target("")
        with self.assertRaises(ProviderHttpError):
            telegram.parse_target("??")

    def test_serialize_message_media_and_invite(self) -> None:
        doc = SimpleNamespace(
            id=5,
            mime_type="application/zip",
            size=10,
            attributes=[SimpleNamespace(file_name="poc.zip")],
        )
        msg = _msg(media=SimpleNamespace(document=doc))
        peers = {("channel", 99): _channel(), ("user", 7): _user()}
        parsed = telegram.serialize_message(msg, peers)
        assert parsed is not None
        self.assertEqual(parsed["media"]["name"], "poc.zip")
        self.assertEqual(parsed["url"], "https://t.me/rev/11")
        photo = telegram.serialize_media(
            SimpleNamespace(
                photo=SimpleNamespace(id=3, sizes=[SimpleNamespace(size=99)])
            )
        )
        self.assertEqual(photo["type"], "photo")
        self.assertEqual(photo["mime"], "image/jpeg")
        self.assertEqual(photo["size"], 99)
        web = telegram.serialize_media(
            SimpleNamespace(webpage=SimpleNamespace(url="https://e.tld", title="E"))
        )
        self.assertEqual(web["type"], "web_page")
        self.assertEqual(web["url"], "https://e.tld")
        self.assertIsNone(telegram.serialize_message(SimpleNamespace(id=None)))
        already = telegram.serialize_invite(SimpleNamespace(chat=_channel()))
        already["status"] = telegram.serialize_invite(
            type("ChatInviteAlready", (), {"chat": _channel()})()
        )["status"]
        self.assertEqual(already["status"], "already_member")
        peek = type("ChatInvitePeek", (), {"chat": _channel(), "expires": 1})()
        self.assertEqual(telegram.serialize_invite(peek)["status"], "peek")
        preview = SimpleNamespace(
            title="G",
            about="a",
            participants_count=2,
            request_needed=True,
            channel=True,
            broadcast=False,
            public=True,
            megagroup=True,
        )
        self.assertTrue(telegram.serialize_invite(preview)["request_needed"])


class KeyTests(unittest.TestCase):
    def test_telegram_keys(self) -> None:
        with self.assertRaises(MissingKeyError):
            require_telegram_app({})
        with self.assertRaises(MissingKeyError):
            require_telegram_app({"TELEGRAM_API_ID": "x", "TELEGRAM_API_HASH": "h"})
        self.assertEqual(
            require_telegram_app({"TELEGRAM_API_ID": "1", "TELEGRAM_API_HASH": "h"}),
            (1, "h"),
        )
        self.assertEqual(optional_telegram_session({}), "")
        with self.assertRaises(MissingKeyError):
            require_telegram_session({"RESEARCH_CLI_NO_ENV_FILE": "1"})
        self.assertEqual(require_telegram_session({"TELEGRAM_SESSION": "S"}), "S")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "telegram.session"
            path.write_bytes(b"data")
            self.assertEqual(
                require_telegram_session({"TELEGRAM_SESSION_FILE": str(path)}),
                "",
            )


class ClientOpTests(unittest.TestCase):
    def test_no_join_in_source(self) -> None:
        src = Path(telegram.__file__).read_text(encoding="utf-8")
        self.assertNotIn("JoinChannel", src)
        self.assertNotIn("ImportChatInvite", src)
        self.assertNotIn("bot_token", src)

    def test_discover_me_history_resolve(self) -> None:
        client = FakeClient(
            ContactsSearchRequest=lambda req: SimpleNamespace(users=[_user()], chats=[_channel()]),
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[_user()],
            ),
            GetHistoryRequest=lambda req: _messages_result(_msg(id=2)),
            SearchRequest=lambda req: _messages_result(_msg(id=3, message="hit")),
            CheckChatInviteRequest=lambda req: SimpleNamespace(
                title="Priv",
                about="x",
                participants_count=9,
                request_needed=True,
                channel=True,
                broadcast=False,
                public=False,
                megagroup=True,
            ),
        )
        factory = _factory(client)
        kw = dict(api_id=1, api_hash="h", session="S", client_factory=factory)
        found = telegram.discover("reverse engineering", **kw)
        self.assertEqual(found["chats"][0]["username"], "rev")
        self.assertEqual(telegram.me(**kw)["user"]["username"], "me")
        hist = telegram.history("@durov", **kw)
        self.assertEqual(hist["results"][0]["id"], 2)
        searched = telegram.history("https://t.me/durov/9", search_query="hit", **kw)
        self.assertEqual(searched["results"][0]["text"], "hit")
        resolved = telegram.resolve("durov", **kw)
        self.assertEqual(resolved["peer"]["id"], 99)
        invite = telegram.resolve("https://t.me/+AbCdefgh", **kw)
        self.assertEqual(invite["invite"]["status"], "request_needed")
        self.assertEqual(invite["invite"]["title"], "Priv")
        already = type("ChatInviteAlready", (), {"chat": _channel()})()
        member_client = FakeClient(CheckChatInviteRequest=lambda req: already)
        member = telegram.resolve(
            "https://t.me/joinchat/AbCdefgh",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(member_client),
        )
        self.assertEqual(member["invite"]["status"], "already_member")
        self.assertEqual(member["invite"]["chat"]["username"], "rev")
        with self.assertRaises(ProviderHttpError):
            telegram.history("https://t.me/+AbCdefgh", **kw)
        with self.assertRaises(ProviderHttpError):
            telegram.discover("", **kw)

    def test_login_and_download(self) -> None:
        client = FakeClient()
        sent = telegram.login(
            phone="+15551212",
            api_id=1,
            api_hash="h",
            session="OLDSESS",
            session_file="/tmp/does-not-matter.session",
            client_factory=_factory(client),
        )
        self.assertEqual(sent["status"], "code_sent")
        self.assertEqual(sent["phone_code_hash"], "HASH")
        authed = telegram.login(
            phone="+15551212",
            api_id=1,
            api_hash="h",
            code="11111",
            phone_code_hash="HASH",
            client_factory=_factory(client),
        )
        self.assertEqual(authed["status"], "authorized")
        self.assertEqual(authed["session"], "SESS")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "env"
            written = telegram.login(
                phone="+15551212",
                api_id=1,
                api_hash="h",
                client_factory=_factory(client),
                env_path=path,
            )
            self.assertEqual(written["status"], "code_sent")
            self.assertEqual(written["env_file"], str(path))
            self.assertNotIn("session", written)
            parsed = parse_env_file(path)
            self.assertEqual(parsed["TELEGRAM_API_ID"], "1")
            self.assertEqual(parsed["TELEGRAM_PHONE_CODE_HASH"], "HASH")
            done = telegram.login(
                phone="+15551212",
                api_id=1,
                api_hash="h",
                code="11111",
                phone_code_hash="HASH",
                client_factory=_factory(client),
                env_path=path,
            )
            self.assertEqual(done["status"], "authorized")
            parsed = parse_env_file(path)
            self.assertEqual(parsed["TELEGRAM_SESSION"], "SESS")
            self.assertNotIn("TELEGRAM_PHONE_CODE_HASH", parsed)

        class Needed(Exception):
            pass

        Needed.__name__ = "SessionPasswordNeededError"

        def need_password(_kwargs: object) -> object:
            raise Needed()

        pw_client = FakeClient(sign_in=need_password)
        needed = telegram.login(
            phone="+1",
            api_id=1,
            api_hash="h",
            code="1",
            client_factory=_factory(pw_client),
        )
        self.assertEqual(needed["status"], "password_needed")

        with tempfile.TemporaryDirectory() as raw:
            dest_dir = Path(raw)
            doc = SimpleNamespace(
                id=5,
                mime_type="application/zip",
                size=4,
                attributes=[SimpleNamespace(file_name="poc.zip")],
            )
            msg = _msg(media=SimpleNamespace(document=doc))
            dl = FakeClient(
                ResolveUsernameRequest=lambda req: SimpleNamespace(
                    peer=SimpleNamespace(channel_id=99),
                    chats=[_channel()],
                    users=[_user()],
                ),
                get_messages=lambda peer, ids: msg,
            )
            out = telegram.download(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                output=str(dest_dir),
                client_factory=_factory(dl),
            )
            self.assertEqual(out["filename"], "poc.zip")
            self.assertTrue(Path(out["path"]).is_file())
            self.assertEqual(out["message"]["chat"]["username"], "rev")
            self.assertEqual(out["message"]["url"], "https://t.me/rev/11")
            self.assertEqual(out["message"]["media"]["mime"], "application/zip")
            self.assertEqual(out["message"]["media"]["name"], "poc.zip")
            self.assertEqual(out["message"]["media"]["size"], 4)
        empty = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            get_messages=lambda peer, ids: _msg(media=None),
        )
        with self.assertRaises(ProviderHttpError):
            telegram.download(
                "11",
                chat="@rev",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(empty),
            )
        with self.assertRaises(ProviderHttpError):
            telegram.download(
                "@rev",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(empty),
            )
        with tempfile.TemporaryDirectory() as raw:
            dest_dir = Path(raw)
            already = type("ChatInviteAlready", (), {"chat": _channel()})()
            member = FakeClient(
                CheckChatInviteRequest=lambda req: already,
                get_messages=lambda peer, ids: msg,
            )
            invited = telegram.download(
                "https://t.me/joinchat/AbCdefgh/11",
                api_id=1,
                api_hash="h",
                session="S",
                output=str(dest_dir),
                client_factory=_factory(member),
            )
            self.assertEqual(invited["filename"], "poc.zip")
        outsider = FakeClient(
            CheckChatInviteRequest=lambda req: SimpleNamespace(title="Priv"),
        )
        with self.assertRaises(ProviderHttpError) as ctx:
            telegram.download(
                "https://t.me/joinchat/AbCdefgh/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(outsider),
            )
        self.assertIn("not a member", str(ctx.exception).lower())
        page = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[_user()],
            ),
            get_messages=lambda peer, ids: _msg(
                media=SimpleNamespace(
                    webpage=SimpleNamespace(url="https://e.tld", title="E")
                )
            ),
        )
        with self.assertRaises(ProviderHttpError) as web_ctx:
            telegram.download(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(page),
            )
        self.assertIn("no media", str(web_ctx.exception).lower())
        got = telegram.get(
            "https://t.me/rev/11",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(dl),
        )
        self.assertEqual(got["operation"], "get")
        self.assertTrue(got["has_media"])
        self.assertEqual(got["media"]["name"], "poc.zip")
        self.assertEqual(got["message"]["chat"]["username"], "rev")
        stripped = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[],
                users=[],
            ),
            get_input_entity=lambda item: SimpleNamespace(channel_id=99),
            get_messages=lambda peer, ids: _msg(media=None),
        )
        # ResolveUsername without a Channel username still stamps @ from the URL.
        with self.assertRaises(ProviderHttpError):
            telegram.get(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(stripped),
            )
        stamped = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[SimpleNamespace(id=99, broadcast=True)],
                users=[],
            ),
            get_input_entity=lambda item: SimpleNamespace(channel_id=99),
            get_messages=lambda peer, ids: _msg(media=None),
        )
        text_got = telegram.get(
            "https://t.me/rev/11",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(stamped),
        )
        self.assertFalse(text_got["has_media"])
        self.assertEqual(text_got["message"]["chat"]["username"], "rev")
        self.assertEqual(text_got["message"]["url"], "https://t.me/rev/11")
        gone_client = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            get_messages=lambda peer, ids: type("MessageEmpty", (), {"id": 11})(),
        )
        with self.assertRaises(ProviderHttpError) as gone:
            telegram.get(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(gone_client),
            )
        self.assertIn("deleted", str(gone.exception).lower())
        class Expired(Exception):
            pass

        Expired.__name__ = "InviteHashExpiredError"

        expired = FakeClient(
            CheckChatInviteRequest=lambda req: (_ for _ in ()).throw(Expired("expired"))
        )
        classified = telegram.resolve(
            "https://t.me/joinchat/AbCdefgh",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(expired),
        )
        self.assertEqual(classified["invite"]["status"], "expired")
        video = telegram.serialize_media(
            SimpleNamespace(
                document=SimpleNamespace(
                    id=1,
                    mime_type="video/mp4",
                    size=9,
                    attributes=[type("DocumentAttributeVideo", (), {})()],
                )
            )
        )
        self.assertEqual(video["type"], "video")
        self.assertTrue(telegram.media_is_file(video))
        self.assertFalse(
            telegram.media_is_file(
                telegram.serialize_media(
                    SimpleNamespace(webpage=SimpleNamespace(url="https://e.tld", title="E"))
                )
            )
        )
        self.assertEqual(telegram.mapped_error_body(Expired("x")), "expired invite")
        self.assertEqual(
            telegram.mapped_error_body(
                RuntimeError("The provided authorization is invalid (ImportAuthorizationRequest)")
            ),
            "session busy",
        )

        class NotMember(Exception):
            pass

        NotMember.__name__ = "UserNotParticipantError"
        self.assertEqual(
            telegram.mapped_error_body(NotMember("USER_NOT_PARTICIPANT")),
            "not a member",
        )

        class Gone(Exception):
            pass

        Gone.__name__ = "MessageIdInvalidError"
        self.assertEqual(
            telegram.mapped_error_body(Gone("MESSAGE_ID_INVALID")), "deleted"
        )
        self.assertEqual(
            telegram.mapped_error_body(RuntimeError("has no downloadable media")),
            "no media",
        )
        with self.assertRaises(ProviderHttpError):
            telegram.login(phone="", api_id=1, api_hash="h", client_factory=_factory(client))

    def test_get_many_one_client_and_failed_download_unlinks(self) -> None:
        client = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            get_messages=lambda peer, ids: _msg(id=int(ids), media=None),
        )
        out = telegram.get_many(
            ["https://t.me/rev/11", "https://t.me/rev/12"],
            api_id=1,
            api_hash="h",
            session="S",
            jobs=4,
            client_factory=_factory(client),
        )
        self.assertEqual(client.connects, 1)
        self.assertEqual([item["id"] for item in out], [11, 12])
        gone = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            get_messages=lambda peer, ids: type("MessageEmpty", (), {"id": ids})(),
        )
        missed = telegram.get_many(
            ["https://t.me/rev/11"],
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(gone),
        )
        self.assertEqual(missed[0]["error"], "deleted")

        def boom(_msg: object, file: str | None = None) -> str:
            path = Path(file or "out.bin")
            path.write_bytes(b"")
            raise RuntimeError(
                "The provided authorization is invalid (caused by ImportAuthorizationRequest)"
            )

        doc = SimpleNamespace(
            id=5,
            mime_type="application/zip",
            size=4,
            attributes=[SimpleNamespace(file_name="poc.zip")],
        )
        msg = _msg(media=SimpleNamespace(document=doc))
        flaky = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            get_messages=lambda peer, ids: msg,
            download_media=boom,
        )
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            saved = telegram.download_many(
                [("https://t.me/rev/11", str(dest))],
                api_id=1,
                api_hash="h",
                session="S",
                jobs=2,
                client_factory=_factory(flaky),
            )
            self.assertEqual(saved[0]["error"], "session busy")
            self.assertEqual(list(dest.iterdir()), [])
        self.assertEqual(telegram.get_many([], api_id=1, api_hash="h", session="S"), [])

    def test_errors_unauthorized_flood_expired(self) -> None:
        denied = FakeClient(authorized=False)
        with self.assertRaises(MissingKeyError):
            telegram.me(api_id=1, api_hash="h", session="S", client_factory=_factory(denied))

        class Flood(Exception):
            seconds = 9

        Flood.__name__ = "FloodWaitError"

        def boom(_req: object) -> object:
            raise Flood()

        flooded = FakeClient(SearchRequest=boom)
        with self.assertRaises(ProviderHttpError) as flood_ctx:
            telegram.discover(
                "q", api_id=1, api_hash="h", session="S", client_factory=_factory(flooded)
            )
        self.assertIn("FLOOD_WAIT", str(flood_ctx.exception))

        class Dead(Exception):
            pass

        Dead.__name__ = "AuthKeyUnregisteredError"

        def dead(_req: object) -> object:
            raise Dead()

        expired = FakeClient(SearchRequest=dead)
        with self.assertRaises(MissingKeyError):
            telegram.discover(
                "q", api_id=1, api_hash="h", session="S", client_factory=_factory(expired)
            )

    def test_missing_telethon_import(self) -> None:
        telegram._TL = None
        with patch.dict(sys.modules, {"telethon": None}):
            with self.assertRaises(ProviderHttpError) as ctx:
                telegram._telethon()
            self.assertIn("telethon is not installed", str(ctx.exception))
        telegram._TL = None


class ExtraBranchTests(unittest.TestCase):
    def test_helpers_and_filters(self) -> None:
        self.assertIsNone(telegram._iso(None))
        self.assertTrue(telegram._iso(datetime(2026, 1, 1)).startswith("2026"))
        self.assertEqual(telegram._iso("x"), "x")
        self.assertIsNone(telegram._int(True))
        self.assertEqual(telegram._int("4"), 4)
        self.assertIsNone(telegram._int("no"))
        self.assertEqual(
            telegram._chat_url(None, 99, 3), "https://t.me/c/99/3"
        )
        self.assertIsNone(telegram._chat_url(None, None, 1))
        self.assertEqual(telegram._peer_kind_id(None), (None, None))
        self.assertEqual(
            telegram._peer_kind_id(SimpleNamespace(chat_id=8)), ("group", 8)
        )
        self.assertEqual(
            telegram._peer_kind_id(SimpleNamespace(id=2, megagroup=True)),
            ("group", 2),
        )
        self.assertEqual(
            telegram._peer_kind_id(SimpleNamespace(id=3, first_name="A")),
            ("user", 3),
        )
        self.assertEqual(
            telegram._peer_kind_id(SimpleNamespace(id=4)), ("group", 4)
        )
        self.assertEqual(telegram._peer_kind_id(SimpleNamespace()), (None, None))
        bot = telegram.serialize_user(
            SimpleNamespace(
                id=1, username="b", first_name="B", last_name="", bot=True, phone="9"
            )
        )
        self.assertTrue(bot["bot"])
        prem = telegram.serialize_user(
            SimpleNamespace(
                id=2, username="p", first_name="P", last_name="", bot=False, premium=True
            )
        )
        self.assertTrue(prem["premium"])
        mega = telegram.serialize_chat(
            SimpleNamespace(id=1, title="G", megagroup=True, username=None)
        )
        self.assertTrue(mega["megagroup"])
        self.assertEqual(telegram.serialize_media(SimpleNamespace())["type"], "SimpleNamespace")
        self.assertIsNone(telegram._session_string(SimpleNamespace(session=None)))
        self.assertEqual(
            telegram._dest_path(None, "a.bin").name, "a.bin"
        )
        photo_msg = _msg(media=SimpleNamespace(photo=SimpleNamespace(id=1)))
        self.assertTrue(telegram._media_filename(photo_msg, 11).endswith(".jpg"))
        img_doc = _msg(
            media=SimpleNamespace(
                document=SimpleNamespace(
                    id=1, mime_type="image/png", size=1, attributes=[]
                )
            )
        )
        self.assertTrue(telegram._media_filename(img_doc, 11).endswith(".jpg"))
        with self.assertRaises(ProviderHttpError) as rpc:
            telegram._raise_rpc(RuntimeError("nope"))
        self.assertIn("nope", str(rpc.exception))
        client = telegram.default_client("", 1, "hash", 0)
        self.assertIsNotNone(client)
        self.assertEqual(type(client.session).__name__, "StringSession")

    def test_session_file_loads_as_string_session_for_parallel(self) -> None:
        import os
        from concurrent.futures import ThreadPoolExecutor

        from telethon.crypto import AuthKey
        from telethon.sessions import SQLiteSession, StringSession

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "telegram.session"
            sql = SQLiteSession(str(path))
            sql.set_dc(2, "149.154.167.51", 443)
            sql.auth_key = AuthKey(data=os.urandom(256))
            sql.save()
            sql.close()
            dumped = telegram._sqlite_to_string(path)
            self.assertTrue(dumped)

            def load(_n: int) -> str:
                sess = telegram._load_string_session("", path)
                return type(sess).__name__

            with ThreadPoolExecutor(max_workers=4) as pool:
                kinds = list(pool.map(load, range(8)))
            self.assertEqual(set(kinds), {"StringSession"})
            c1 = telegram.default_client("", 1, "h", 5, session_file=str(path))
            c2 = telegram.default_client("", 1, "h", 5, session_file=str(path))
            self.assertEqual(type(c1.session).__name__, "StringSession")
            self.assertEqual(type(c2.session).__name__, "StringSession")
            telegram._string_to_sqlite(dumped, path)
            again = telegram._sqlite_to_string(path)
            self.assertEqual(again, dumped)
            roundtrip = StringSession(dumped)
            self.assertEqual(roundtrip.dc_id, 2)

    def test_connect_call_input_peer_and_login_password(self) -> None:
        class Needed(Exception):
            pass

        Needed.__name__ = "SessionPasswordNeededError"
        state = {"n": 0}

        def sign_in(kwargs: object) -> object:
            state["n"] += 1
            if state["n"] == 1:
                raise Needed()
            return SimpleNamespace(
                id=1, username="me", first_name="Me", last_name="", bot=False, phone="1"
            )

        pw = FakeClient(sign_in=sign_in)
        out = telegram.login(
            phone="+1",
            api_id=1,
            api_hash="h",
            code="1",
            password="secret",
            client_factory=_factory(pw),
        )
        self.assertEqual(out["status"], "authorized")

        def other_err(_kwargs: object) -> object:
            raise RuntimeError("bad code")

        with self.assertRaises(ProviderHttpError):
            telegram.login(
                phone="+1",
                api_id=1,
                api_hash="h",
                code="1",
                client_factory=_factory(FakeClient(sign_in=other_err)),
            )

        class BoomMe(FakeClient):
            async def get_me(self) -> object:
                raise RuntimeError("offline")

        with self.assertRaises(ProviderHttpError):
            telegram.me(
                api_id=1, api_hash="h", session="S", client_factory=_factory(BoomMe())
            )

        class KeyCall(FakeClient):
            async def __call__(self, request: object) -> object:
                raise MissingKeyError("telegram", ("TELEGRAM_SESSION",))

        with self.assertRaises(MissingKeyError):
            telegram.discover(
                "q",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(KeyCall()),
            )

        miss = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=1), chats=[], users=[]
            )
        )
        with self.assertRaises(ProviderHttpError):
            telegram.history(
                "@missing",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(miss),
            )

        class Internal(FakeClient):
            async def get_input_entity(self, item: object) -> object:
                raise RuntimeError("no hash")

        with self.assertRaises(ProviderHttpError):
            telegram.history(
                "https://t.me/c/99/1",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(Internal()),
            )

        ok_internal = FakeClient(
            GetHistoryRequest=lambda req: _messages_result(_msg()),
        )
        hist = telegram.history(
            "https://t.me/c/99",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(ok_internal),
        )
        self.assertEqual(hist["operation"], "history")

        with self.assertRaises(ProviderHttpError):
            telegram.resolve(
                "99",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(FakeClient()),
            )

        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / "file.bin"
            doc = SimpleNamespace(
                id=5, mime_type="application/zip", size=4, attributes=[]
            )
            msg = _msg(media=SimpleNamespace(document=doc))
            dl = FakeClient(
                get_messages=lambda peer, ids: [msg],
            )
            out = telegram.download(
                "https://t.me/c/99/11",
                api_id=1,
                api_hash="h",
                session="S",
                output=str(dest),
                client_factory=_factory(dl),
            )
            self.assertEqual(out["operation"], "download")

        empty_list = FakeClient(get_messages=lambda peer, ids: [])
        with self.assertRaises(ProviderHttpError):
            telegram.download(
                "11",
                chat="@rev",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(
                    FakeClient(
                        ResolveUsernameRequest=lambda req: SimpleNamespace(
                            peer=SimpleNamespace(channel_id=99),
                            chats=[_channel()],
                            users=[],
                        ),
                        get_messages=lambda peer, ids: [],
                    )
                ),
            )
        self.assertIs(empty_list, empty_list)
        with self.assertRaises(ProviderHttpError):
            telegram.download(
                "11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(FakeClient()),
            )

        class BoomDl(FakeClient):
            async def get_messages(self, peer: object, ids: object = None) -> object:
                raise RuntimeError("io")

        with self.assertRaises(ProviderHttpError):
            telegram.download(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(
                    BoomDl(
                        ResolveUsernameRequest=lambda req: SimpleNamespace(
                            peer=SimpleNamespace(channel_id=99),
                            chats=[_channel()],
                            users=[],
                        )
                    )
                ),
            )

        class NoDisc:
            session = SimpleNamespace(save=lambda: "S")

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                return True

            async def get_me(self) -> object:
                return _user()

        out_me = telegram.me(
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=lambda *a: NoDisc(),
        )
        self.assertEqual(out_me["user"]["username"], "alice")

        with patch(
            "research_cli.providers.telegram.asyncio.get_running_loop",
            return_value=object(),
        ):
            with self.assertRaises(ProviderHttpError) as loop_ctx:
                telegram._run("unused")
            self.assertIn("event loop", str(loop_ctx.exception))

        from telethon.errors import SessionPasswordNeededError

        def need_real(_kwargs: object) -> object:
            raise SessionPasswordNeededError("login")

        needed = telegram.login(
            phone="+1",
            api_id=1,
            api_hash="h",
            code="1",
            client_factory=_factory(FakeClient(sign_in=need_real)),
        )
        self.assertEqual(needed["status"], "password_needed")
        state = {"n": 0}

        def then_ok(kwargs: object) -> object:
            state["n"] += 1
            if state["n"] == 1:
                raise SessionPasswordNeededError("login")
            return FakeClient().me

        authed = telegram.login(
            phone="+1",
            api_id=1,
            api_hash="h",
            code="1",
            password="pw",
            client_factory=_factory(FakeClient(sign_in=then_ok)),
        )
        self.assertEqual(authed["status"], "authorized")

        class HttpCall(FakeClient):
            async def __call__(self, request: object) -> object:
                raise ProviderHttpError("telegram", 1, "x")

        with self.assertRaises(ProviderHttpError):
            telegram.discover(
                "q",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(HttpCall()),
            )

        class MeKey(FakeClient):
            async def get_me(self) -> object:
                raise MissingKeyError("telegram", ("TELEGRAM_SESSION",))

        with self.assertRaises(MissingKeyError):
            telegram.me(
                api_id=1, api_hash="h", session="S", client_factory=_factory(MeKey())
            )

        class MeHttp(FakeClient):
            async def get_me(self) -> object:
                raise ProviderHttpError("telegram", 1, "x")

        with self.assertRaises(ProviderHttpError):
            telegram.me(
                api_id=1, api_hash="h", session="S", client_factory=_factory(MeHttp())
            )

        no_get = FakeClient(
            ResolveUsernameRequest=lambda req: SimpleNamespace(
                peer=SimpleNamespace(channel_id=99),
                chats=[_channel()],
                users=[],
            ),
            GetHistoryRequest=lambda req: _messages_result(_msg()),
        )
        no_get.get_input_entity = None  # type: ignore[assignment]
        hist = telegram.history(
            "@rev",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(no_get),
        )
        self.assertEqual(hist["operation"], "history")

        internal_none = FakeClient()
        internal_none.get_input_entity = None  # type: ignore[assignment]
        with self.assertRaises(ProviderHttpError):
            telegram.history(
                "https://t.me/c/99",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(internal_none),
            )

        by_id = FakeClient(GetHistoryRequest=lambda req: _messages_result(_msg()))
        by_id.get_input_entity = lambda item: item  # type: ignore[assignment]
        telegram.history(
            "99",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(by_id),
        )
        telegram.history(
            "99",
            api_id=1,
            api_hash="h",
            session="S",
            client_factory=_factory(
                FakeClient(GetHistoryRequest=lambda req: _messages_result(_msg()))
            ),
        )

        async def invite_peer() -> None:
            await telegram._input_peer(FakeClient(), {"kind": "invite", "hash": "x"})

        with self.assertRaises(ProviderHttpError):
            telegram._run(invite_peer())
        id_none = FakeClient()
        id_none.get_input_entity = None  # type: ignore[assignment]
        with self.assertRaises(ProviderHttpError):
            telegram.history(
                "99",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(id_none),
            )

        class KeyDl(FakeClient):
            async def get_messages(self, peer: object, ids: object = None) -> object:
                raise MissingKeyError("telegram", ("TELEGRAM_SESSION",))

        with self.assertRaises(MissingKeyError):
            telegram.download(
                "https://t.me/rev/11",
                api_id=1,
                api_hash="h",
                session="S",
                client_factory=_factory(
                    KeyDl(
                        ResolveUsernameRequest=lambda req: SimpleNamespace(
                            peer=SimpleNamespace(channel_id=99),
                            chats=[_channel()],
                            users=[],
                        )
                    )
                ),
            )

        old_policy = asyncio.get_event_loop_policy()
        try:
            with patch("research_cli.providers.telegram.os.name", "nt"):
                with patch.object(
                    asyncio,
                    "WindowsSelectorEventLoopPolicy",
                    asyncio.DefaultEventLoopPolicy,
                    create=True,
                ):
                    async def one() -> int:
                        return 1

                    self.assertEqual(telegram._run(one()), 1)
        finally:
            asyncio.set_event_loop_policy(old_policy)


class DispatchTests(unittest.TestCase):
    def test_cli_dispatch_each_operation(self) -> None:
        from unittest.mock import patch

        from research_cli.cli import _dispatch_telegram, build_parser

        env = {
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "h",
            "TELEGRAM_SESSION": "S",
        }
        parser = build_parser()
        cases = [
            (["telegram", "login", "--phone", "+1", "--session", "PEND"], "login"),
            (["telegram", "login", "--code", "12345"], "login"),
            (
                [
                    "telegram",
                    "login",
                    "--api-id",
                    "1",
                    "--api-hash",
                    "h",
                    "--phone",
                    "+1",
                    "--no-write-env",
                ],
                "login",
            ),
            (["telegram", "me"], "me"),
            (["telegram", "discover", "q"], "discover"),
            (["telegram", "history", "@durov", "--search", "x"], "history"),
            (["telegram", "resolve", "durov"], "resolve"),
            (["telegram", "get", "https://t.me/durov/1"], "get"),
            (["telegram", "download", "https://t.me/durov/1", "-o", "/tmp"], "download"),
        ]
        for argv, op in cases:
            args = parser.parse_args(argv)
            with patch(
                f"research_cli.cli.telegram.{op}", return_value={"operation": op}
            ):
                payload = _dispatch_telegram(args, env, None, 30.0)
            self.assertEqual(payload["operation"], op)
        args = parser.parse_args(["telegram", "login", "--phone", "+1", "--no-write-env"])
        with patch(
            "research_cli.cli.telegram.login", return_value={"operation": "login"}
        ) as fn:
            _dispatch_telegram(args, env, None, 30.0)
        self.assertIsNone(fn.call_args.kwargs["env_path"])
        self.assertIsNone(fn.call_args.kwargs.get("session_file"))
        pending = dict(env)
        pending["TELEGRAM_PHONE"] = "+1999"
        pending["TELEGRAM_PHONE_CODE_HASH"] = "HH"
        args = parser.parse_args(["telegram", "login", "--code", "11111"])
        with patch(
            "research_cli.cli.telegram.login", return_value={"operation": "login"}
        ) as fn:
            _dispatch_telegram(args, pending, None, 30.0)
        self.assertEqual(fn.call_args.kwargs["phone"], "+1999")
        self.assertEqual(fn.call_args.kwargs["phone_code_hash"], "HH")
        import argparse

        with self.assertRaises(ValueError):
            _dispatch_telegram(
                argparse.Namespace(operation="join"),
                env,
                None,
                30.0,
            )


if __name__ == "__main__":
    unittest.main()
