from __future__ import annotations

import io
import json
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.cli import main  # noqa: E402
from research_cli.errors import UpdateError  # noqa: E402
from research_cli.http import HttpResponse  # noqa: E402
from research_cli.update import (  # noqa: E402
    WAIT_PID_ENV,
    Install,
    asset_name,
    detect_kind,
    parse_version,
    replace_executable,
    run_self_update,
    spawn_background_update,
    update_command,
    version_is_newer,
    wait_for_pid,
)

from fixtures import BGPT_PAYLOAD, BGPT_TITLE  # noqa: E402


class MapTransport:
    def __init__(self, mapping: dict[str, HttpResponse]) -> None:
        self.mapping = mapping
        self.urls: list[str] = []

    def __call__(self, request):
        self.urls.append(request.url)
        response = self.mapping.get(request.url)
        if response is None:
            return HttpResponse(404, {}, b'{"message":"Not Found"}')
        return response


def _json_response(payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def _release(tag: str, assets: list[dict[str, object]]) -> dict[str, object]:
    return {"tag_name": tag, "assets": assets}


def _asset(name: str, url: str, body: bytes) -> dict[str, object]:
    return {"name": name, "browser_download_url": url, "size": len(body)}


LATEST_API = (
    "https://api.github.com/repos/ErcinDedeoglu/research-cli/releases/latest"
)
DARWIN_URL = (
    "https://github.com/ErcinDedeoglu/research-cli/releases/download/"
    "v9.9.9/research-cli-Darwin-arm64"
)
PYZ_URL = (
    "https://github.com/ErcinDedeoglu/research-cli/releases/download/"
    "v9.9.9/research-cli.pyz"
)


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self) -> None:
        self.assertEqual(parse_version("v0.2.0"), (0, 2, 0))
        self.assertEqual(parse_version("0.1.0"), (0, 1, 0))
        self.assertTrue(version_is_newer("v0.2.0", "0.1.0"))
        self.assertFalse(version_is_newer("v0.1.0", "0.1.0"))
        self.assertFalse(version_is_newer("0.1.0", "0.2.0"))


class AssetNameTests(unittest.TestCase):
    def test_release_yml_names(self) -> None:
        cases = [
            ("frozen", "Darwin", "arm64", "research-cli-Darwin-arm64"),
            ("frozen", "Darwin", "x86_64", "research-cli-Darwin-x86_64"),
            ("frozen", "Linux", "x86_64", "research-cli-Linux-x86_64"),
            ("frozen", "Linux", "aarch64", "research-cli-Linux-aarch64"),
            ("frozen", "Linux", "arm64", "research-cli-Linux-aarch64"),
            ("frozen", "Windows", "AMD64", "research-cli-Windows-x86_64.exe"),
            ("zipapp", "Darwin", "arm64", "research-cli.pyz"),
            ("zipapp", "Windows", "AMD64", "research-cli.pyz"),
        ]
        for kind, system, machine, expected in cases:
            self.assertEqual(asset_name(kind, system, machine), expected)

    def test_unknown_arch_errors(self) -> None:
        with self.assertRaises(UpdateError):
            asset_name("frozen", "Linux", "riscv64")


class DetectKindTests(unittest.TestCase):
    def test_frozen_zipapp_source(self) -> None:
        self.assertEqual(detect_kind(frozen=True, argv0="research-cli"), "frozen")
        self.assertEqual(
            detect_kind(frozen=False, argv0="/tmp/research-cli.pyz"), "zipapp"
        )
        self.assertEqual(
            detect_kind(frozen=False, argv0=sys.executable), "source"
        )


class ReplaceTests(unittest.TestCase):
    def test_unix_replace_preserves_mode(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "research-cli"
            target.write_bytes(b"old")
            target.chmod(0o754)
            replace_executable(target, b"new-bytes", windows=False)
            self.assertEqual(target.read_bytes(), b"new-bytes")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o754)

    def test_windows_rename_dance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "research-cli.exe"
            target.write_bytes(b"old-exe")
            replace_executable(target, b"new-exe", windows=True)
            self.assertEqual(target.read_bytes(), b"new-exe")
            leftover = target.parent / f".{target.name}.old"
            self.assertTrue(leftover.is_file())
            self.assertEqual(leftover.read_bytes(), b"old-exe")


class SelfUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.cache = self.dir / "cache"
        self.environ = {"RESEARCH_CLI_CACHE_DIR": str(self.cache)}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _install(self, kind: str = "frozen", name: str = "research-cli") -> Install:
        target = self.dir / name
        target.write_bytes(b"old-binary")
        target.chmod(0o755)
        system = "Darwin"
        machine = "arm64"
        if kind == "zipapp":
            target = self.dir / "research-cli.pyz"
            target.write_bytes(b"old-pyz")
        return Install(kind, target, system, machine)

    def test_source_does_not_hit_network(self) -> None:
        transport = MapTransport({})
        payload = run_self_update(
            environ=self.environ,
            transport=transport,
            install=Install("source", None, "Darwin", "arm64"),
            current_version="0.1.0",
        )
        self.assertEqual(payload["status"], "unsupported")
        self.assertIn("pip install", payload["hint"])
        self.assertEqual(transport.urls, [])

    def test_frozen_replaces_when_newer(self) -> None:
        install = self._install()
        body = b"new-frozen-binary"
        release = _release(
            "v9.9.9",
            [_asset("research-cli-Darwin-arm64", DARWIN_URL, body)],
        )
        transport = MapTransport(
            {
                LATEST_API: _json_response(release),
                DARWIN_URL: HttpResponse(200, {}, body),
            }
        )
        payload = run_self_update(
            environ=self.environ,
            transport=transport,
            install=install,
            current_version="0.1.0",
        )
        self.assertEqual(payload["status"], "updated")
        self.assertEqual(payload["from"], "0.1.0")
        self.assertEqual(install.path.read_bytes(), body)
        self.assertEqual(transport.urls, [LATEST_API, DARWIN_URL])

    def test_force_replaces_even_when_tag_matches(self) -> None:
        install = self._install()
        body = b"same-tag-new-bytes"
        release = _release(
            "v0.1.0",
            [_asset("research-cli-Darwin-arm64", DARWIN_URL, body)],
        )
        transport = MapTransport(
            {
                LATEST_API: _json_response(release),
                DARWIN_URL: HttpResponse(200, {}, body),
            }
        )
        payload = run_self_update(
            environ=self.environ,
            transport=transport,
            install=install,
            current_version="0.1.0",
        )
        self.assertEqual(payload["status"], "updated")
        self.assertEqual(install.path.read_bytes(), body)
        self.assertEqual(transport.urls, [LATEST_API, DARWIN_URL])

    def test_busy_lock_does_not_hit_network(self) -> None:
        install = self._install()
        ready = self.dir / "lock-ready"
        stop = self.dir / "lock-stop"
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "\n".join(
                    [
                        "import sys, time",
                        "from pathlib import Path",
                        "sys.path.insert(0, sys.argv[1])",
                        "from research_cli.update import acquire_update_lock",
                        "h = acquire_update_lock(",
                        "    {'RESEARCH_CLI_CACHE_DIR': sys.argv[2]}, blocking=True",
                        ")",
                        "Path(sys.argv[3]).write_text('1')",
                        "while not Path(sys.argv[4]).exists():",
                        "    time.sleep(0.05)",
                        "h.close()",
                    ]
                ),
                str(ROOT / "src"),
                str(self.cache),
                str(ready),
                str(stop),
            ]
        )
        try:
            deadline = time.time() + 5
            while not ready.is_file():
                if time.time() > deadline:
                    self.fail("lock holder did not start")
                time.sleep(0.05)
            transport = MapTransport({})
            payload = run_self_update(
                environ={**self.environ, WAIT_PID_ENV: "0"},
                transport=transport,
                install=install,
                current_version="0.1.0",
            )
            self.assertEqual(payload["status"], "busy")
            self.assertEqual(transport.urls, [])
        finally:
            stop.write_text("1")
            holder.wait(timeout=5)

    def test_zipapp_uses_pyz_asset(self) -> None:
        install = self._install(kind="zipapp")
        body = b"PK\x03\x04new-zipapp"
        release = _release(
            "v9.9.9", [_asset("research-cli.pyz", PYZ_URL, body)]
        )
        transport = MapTransport(
            {
                LATEST_API: _json_response(release),
                PYZ_URL: HttpResponse(200, {}, body),
            }
        )
        payload = run_self_update(
            environ=self.environ,
            transport=transport,
            install=install,
            current_version="0.1.0",
        )
        self.assertEqual(payload["status"], "updated")
        self.assertEqual(payload["asset"], "research-cli.pyz")
        self.assertEqual(install.path.read_bytes(), body)

    def test_missing_release_is_error(self) -> None:
        install = self._install()
        transport = MapTransport(
            {LATEST_API: _json_response({"message": "Not Found"}, status=404)}
        )
        with self.assertRaises(UpdateError) as ctx:
            run_self_update(
                environ=self.environ,
                transport=transport,
                install=install,
                current_version="0.1.0",
            )
        self.assertIn("no GitHub release", str(ctx.exception))

    def test_missing_asset_is_error(self) -> None:
        install = self._install()
        release = _release("v9.9.9", [_asset("research-cli.pyz", PYZ_URL, b"x")])
        transport = MapTransport({LATEST_API: _json_response(release)})
        with self.assertRaises(UpdateError) as ctx:
            run_self_update(
                environ=self.environ,
                transport=transport,
                install=install,
                current_version="0.1.0",
            )
        self.assertIn("research-cli-Darwin-arm64", str(ctx.exception))

    def test_html_download_rejected(self) -> None:
        install = self._install()
        release = _release(
            "v9.9.9",
            [_asset("research-cli-Darwin-arm64", DARWIN_URL, b"<html>")],
        )
        transport = MapTransport(
            {
                LATEST_API: _json_response(release),
                DARWIN_URL: HttpResponse(200, {}, b"<html>login</html>"),
            }
        )
        with self.assertRaises(UpdateError) as ctx:
            run_self_update(
                environ=self.environ,
                transport=transport,
                install=install,
                current_version="0.1.0",
            )
        self.assertIn("HTML", str(ctx.exception))

    def test_invalid_repo_env(self) -> None:
        install = self._install()
        with self.assertRaises(UpdateError):
            run_self_update(
                environ={**self.environ, "RESEARCH_CLI_REPO": "not a repo"},
                transport=MapTransport({}),
                install=install,
            )


class SpawnTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.target = self.dir / "research-cli"
        self.target.write_bytes(b"old")
        self.target.chmod(0o755)
        self.frozen = Install("frozen", self.target, "Darwin", "arm64")
        self.pyz = self.dir / "research-cli.pyz"
        self.pyz.write_bytes(b"old-pyz")
        self.zipapp = Install("zipapp", self.pyz, "Darwin", "arm64")
        self.popen = _Recorder()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_source_does_not_spawn(self) -> None:
        spawned = spawn_background_update(
            environ={},
            install=Install("source", None, "Darwin", "arm64"),
            popen=self.popen,
        )
        self.assertFalse(spawned)
        self.assertEqual(self.popen.calls, [])

    def test_no_update_env_does_not_spawn(self) -> None:
        spawned = spawn_background_update(
            environ={"RESEARCH_CLI_NO_UPDATE": "1"},
            install=self.frozen,
            popen=self.popen,
        )
        self.assertFalse(spawned)
        self.assertEqual(self.popen.calls, [])

    def test_frozen_spawns_detached_self_update(self) -> None:
        spawned = spawn_background_update(
            environ={"RESEARCH_CLI_CACHE_DIR": str(self.dir / "cache")},
            install=self.frozen,
            popen=self.popen,
            parent_pid=4242,
        )
        self.assertTrue(spawned)
        self.assertEqual(len(self.popen.calls), 1)
        cmd, kwargs = self.popen.calls[0]
        self.assertEqual(cmd, [str(self.target), "--self-update"])
        self.assertEqual(kwargs["env"][WAIT_PID_ENV], "4242")
        self.assertNotIn("RESEARCH_CLI_NO_UPDATE", kwargs["env"])
        self.assertTrue(kwargs.get("start_new_session") or kwargs.get("creationflags"))
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)

    def test_zipapp_uses_python_interpreter(self) -> None:
        spawned = spawn_background_update(
            environ={},
            install=self.zipapp,
            popen=self.popen,
            parent_pid=7,
        )
        self.assertTrue(spawned)
        cmd, _kwargs = self.popen.calls[0]
        self.assertEqual(cmd, update_command(self.zipapp))
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[-1], "--self-update")

    def test_wait_for_pid_returns_when_parent_exits(self) -> None:
        ticks: list[int] = []
        states = [True, True, False]

        def running(_pid: int) -> bool:
            return states.pop(0) if states else False

        wait_for_pid(
            1,
            timeout=10,
            running=running,
            sleeper=lambda _s: ticks.append(1),
            clock=lambda: 0.0,
        )
        self.assertEqual(len(ticks), 2)


class AfterCommandTests(unittest.TestCase):
    def _bgpt_transport(self):
        def send(_request):
            return HttpResponse(
                200,
                {"Content-Type": "application/json"},
                json.dumps(BGPT_PAYLOAD).encode("utf-8"),
            )

        return send

    def test_success_emits_json_then_schedules_update(self) -> None:
        seen: list[str] = []
        out = io.StringIO()

        def spy(_environ: dict[str, str]) -> None:
            seen.append(out.getvalue())

        code = main(
            ["bgpt", "search", "q"],
            environ={},
            transport=self._bgpt_transport(),
            stdout=out,
            stderr=io.StringIO(),
            spawn_update=spy,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(seen), 1)
        self.assertIn(BGPT_TITLE, seen[0])
        self.assertIn(BGPT_TITLE, out.getvalue())

    def test_missing_key_still_schedules(self) -> None:
        scheduled: list[int] = []
        code = main(
            ["brave", "search", "q"],
            environ={},
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            spawn_update=lambda _e: scheduled.append(1),
        )
        self.assertEqual(code, 2)
        self.assertEqual(scheduled, [1])

    def test_http_error_still_schedules(self) -> None:
        scheduled: list[int] = []

        def boom(_request):
            return HttpResponse(500, {}, b"nope")

        code = main(
            ["bgpt", "search", "q"],
            environ={},
            transport=boom,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            spawn_update=lambda _e: scheduled.append(1),
        )
        self.assertEqual(code, 1)
        self.assertEqual(scheduled, [1])

    def test_version_help_and_parse_error_still_schedule(self) -> None:
        for argv, expected in (
            (["--version"], 0),
            (["--help"], 0),
            ([], 2),
        ):
            scheduled: list[int] = []
            buf = io.StringIO()
            old_out, old_err = sys.stdout, sys.stderr
            try:
                sys.stdout = buf
                sys.stderr = buf
                code = main(
                    argv,
                    environ={},
                    stdout=buf,
                    stderr=buf,
                    spawn_update=lambda _e: scheduled.append(1),
                )
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
            self.assertEqual(code, expected, argv)
            self.assertEqual(scheduled, [1], argv)

    def test_self_update_does_not_reschedule(self) -> None:
        scheduled: list[int] = []
        code = main(
            ["--self-update"],
            environ={},
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            spawn_update=lambda _e: scheduled.append(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(scheduled, [])

    def test_spawn_failure_does_not_change_exit_code(self) -> None:
        def boom(_environ: dict[str, str]) -> None:
            raise RuntimeError("spawn failed")

        out = io.StringIO()
        code = main(
            ["bgpt", "search", "q"],
            environ={},
            transport=self._bgpt_transport(),
            stdout=out,
            stderr=io.StringIO(),
            spawn_update=boom,
        )
        self.assertEqual(code, 0)
        self.assertIn(BGPT_TITLE, out.getvalue())


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return self


class SelfUpdateCliTests(unittest.TestCase):
    def test_self_update_source_prints_json(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        code = main(["--self-update"], stdout=out, stderr=err, environ={})
        self.assertEqual(code, 0, err.getvalue())
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "unsupported")
        self.assertEqual(payload["kind"], "source")
        self.assertIn("pip install", payload["hint"])


if __name__ == "__main__":
    unittest.main()
