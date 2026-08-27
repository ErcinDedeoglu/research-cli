from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO
from urllib.parse import urlparse

from research_cli import __version__
from research_cli.errors import UpdateError
from research_cli.http import USER_AGENT, HttpRequest, HttpResponse, Transport, urllib_transport

DEFAULT_REPO = "ErcinDedeoglu/research-cli"
DEFAULT_API = "https://api.github.com"
MAX_ASSET_BYTES = 200 * 1024 * 1024
EXPLICIT_TIMEOUT = 60.0
WAIT_PARENT_TIMEOUT = 30.0
WAIT_PID_ENV = "RESEARCH_CLI_UPDATE_WAIT_PID"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TRUTHY = {"1", "true", "yes", "on"}
PopenFn = Callable[..., Any]


@dataclass(frozen=True)
class Install:
    kind: str
    path: Path | None
    system: str
    machine: str


def parse_version(value: str) -> tuple[int, ...]:
    text = value.strip()
    if text[:1] in {"v", "V"}:
        text = text[1:]
    parts: list[int] = []
    for chunk in text.split("."):
        digits = []
        for char in chunk:
            if char.isdigit():
                digits.append(char)
            else:
                break
        parts.append(int("".join(digits)) if digits else 0)
    return tuple(parts) if parts else (0,)


def version_is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def detect_kind(*, frozen: bool | None = None, argv0: str | None = None) -> str:
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
    if frozen:
        return "frozen"
    path = argv0 if argv0 is not None else (sys.argv[0] if sys.argv else "")
    if str(path).endswith(".pyz"):
        return "zipapp"
    return "source"


def current_install(
    *,
    kind: str | None = None,
    path: Path | None = None,
    system: str | None = None,
    machine: str | None = None,
    argv0: str | None = None,
) -> Install:
    resolved_kind = kind or detect_kind(argv0=argv0)
    resolved_path = path
    if resolved_path is None:
        if resolved_kind == "frozen":
            resolved_path = Path(sys.executable)
        elif resolved_kind == "zipapp":
            resolved_path = Path(argv0 if argv0 is not None else sys.argv[0])
    if resolved_path is not None:
        resolved_path = resolved_path.resolve()
    return Install(
        kind=resolved_kind,
        path=resolved_path,
        system=system or platform.system(),
        machine=machine or platform.machine(),
    )


def asset_name(kind: str, system: str, machine: str) -> str:
    if kind == "zipapp":
        return "research-cli.pyz"
    arch = _arch(system, machine)
    if system == "Windows":
        return f"research-cli-Windows-{arch}.exe"
    if system in {"Darwin", "Linux"}:
        return f"research-cli-{system}-{arch}"
    raise UpdateError(f"unsupported platform: {system} {machine}")


def _arch(system: str, machine: str) -> str:
    normalized = machine.lower().replace("-", "_")
    if normalized in {"arm64", "aarch64"}:
        return "aarch64" if system == "Linux" else "arm64"
    if normalized in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    raise UpdateError(f"unsupported architecture: {system} {machine}")


def cache_dir(environ: Mapping[str, str]) -> Path:
    override = (environ.get("RESEARCH_CLI_CACHE_DIR") or "").strip()
    if override:
        return Path(override)
    xdg = (environ.get("XDG_CACHE_HOME") or "").strip()
    if xdg:
        return Path(xdg) / "research-cli"
    if os.name == "nt":
        base = (environ.get("LOCALAPPDATA") or "").strip()
        if base:
            return Path(base) / "research-cli"
        return Path.home() / "AppData" / "Local" / "research-cli"
    return Path.home() / ".cache" / "research-cli"


def updates_disabled(environ: Mapping[str, str]) -> bool:
    value = (environ.get("RESEARCH_CLI_NO_UPDATE") or "").strip().lower()
    return value in _TRUTHY


def _repo(environ: Mapping[str, str]) -> str:
    repo = (environ.get("RESEARCH_CLI_REPO") or DEFAULT_REPO).strip()
    if not _REPO_RE.fullmatch(repo):
        raise UpdateError(f"invalid RESEARCH_CLI_REPO: {repo}")
    return repo


def _api_origin(environ: Mapping[str, str]) -> str:
    return (environ.get("RESEARCH_CLI_GITHUB_API") or DEFAULT_API).rstrip("/")


def _send(
    request: HttpRequest,
    *,
    transport: Transport | None,
    timeout: float,
) -> HttpResponse:
    send = transport if transport is not None else (
        lambda req: urllib_transport(req, timeout=timeout)
    )
    try:
        return send(request)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"github: {exc}") from exc


def fetch_latest_release(
    *,
    environ: Mapping[str, str],
    transport: Transport | None,
    timeout: float,
) -> dict[str, Any] | None:
    url = f"{_api_origin(environ)}/repos/{_repo(environ)}/releases/latest"
    response = _send(
        HttpRequest(
            method="GET",
            url=url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        ),
        transport=transport,
        timeout=timeout,
    )
    if response.status == 404:
        return None
    if response.status >= 400:
        text = response.body.decode("utf-8", errors="replace")[:500]
        raise UpdateError(f"github HTTP {response.status}: {text}")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise UpdateError("github latest release is not JSON") from exc
    if not isinstance(payload, dict):
        raise UpdateError("github latest release is not an object")
    return payload


def choose_asset(release: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        raise UpdateError("github release assets are not a list")
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == name:
            if not asset.get("browser_download_url"):
                raise UpdateError(f"asset {name} has no browser_download_url")
            return asset
    tag = release.get("tag_name") or "unknown"
    raise UpdateError(f"release {tag} has no asset {name}")


def _allowed_download_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        host == "github.com"
        or host.endswith(".github.com")
        or host == "githubusercontent.com"
        or host.endswith(".githubusercontent.com")
    )


def download_asset(
    url: str,
    *,
    transport: Transport | None,
    timeout: float,
) -> bytes:
    if transport is None and not _allowed_download_url(url):
        raise UpdateError(f"refusing download host: {url}")
    response = _send(
        HttpRequest(
            method="GET",
            url=url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/octet-stream",
            },
        ),
        transport=transport,
        timeout=timeout,
    )
    if response.status >= 400:
        text = response.body.decode("utf-8", errors="replace")[:500]
        raise UpdateError(f"download HTTP {response.status}: {text}")
    data = response.body
    if not data:
        raise UpdateError("empty download")
    if len(data) > MAX_ASSET_BYTES:
        raise UpdateError("download too large")
    if data.lstrip()[:1] == b"<":
        raise UpdateError("download looks like HTML, not a binary")
    return data


def replace_executable(
    target: Path, data: bytes, *, windows: bool | None = None
) -> None:
    windows = os.name == "nt" if windows is None else windows
    mode = target.stat().st_mode if target.exists() else 0o755
    tmp = target.parent / f".{target.name}.new"
    old = target.parent / f".{target.name}.old"
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    if windows and target.exists():
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
        os.replace(target, old)
        try:
            os.replace(tmp, target)
        except OSError:
            try:
                os.replace(old, target)
            except OSError:
                pass
            raise
        return
    os.replace(tmp, target)


def cleanup_old_binary(target: Path | None) -> None:
    if target is None:
        return
    old = target.parent / f".{target.name}.old"
    try:
        old.unlink(missing_ok=True)
    except OSError:
        return


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_for_pid(
    pid: int,
    *,
    timeout: float = WAIT_PARENT_TIMEOUT,
    poll: float = 0.05,
    running: Callable[[int], bool] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> None:
    is_running = running or pid_is_running
    deadline = clock() + timeout
    while is_running(pid):
        if clock() >= deadline:
            return
        sleeper(poll)


def wait_for_parent(environ: Mapping[str, str]) -> None:
    raw = (environ.get(WAIT_PID_ENV) or "").strip()
    if not raw:
        return
    try:
        pid = int(raw)
    except ValueError:
        return
    wait_for_pid(pid)


def acquire_update_lock(environ: Mapping[str, str], *, blocking: bool) -> IO[str] | None:
    path = cache_dir(environ) / "update.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+")
    except OSError:
        return None
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            flags = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(handle.fileno(), flags, 1)
        else:
            import fcntl

            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(handle.fileno(), flags)
    except OSError:
        handle.close()
        return None
    return handle


def update_command(install: Install) -> list[str]:
    path = str(install.path)
    if install.kind == "zipapp":
        return [sys.executable, path, "--self-update"]
    return [path, "--self-update"]


def _child_env(environ: Mapping[str, str], parent_pid: int) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in environ.items():
        if key.startswith("RESEARCH_CLI_"):
            env[key] = value
    env[WAIT_PID_ENV] = str(parent_pid)
    env.pop("RESEARCH_CLI_NO_UPDATE", None)
    return env


def spawn_background_update(
    *,
    environ: Mapping[str, str],
    install: Install | None = None,
    popen: PopenFn = subprocess.Popen,
    parent_pid: int | None = None,
) -> bool:
    if updates_disabled(environ):
        return False
    install = install or current_install()
    if install.kind == "source" or install.path is None:
        return False
    cmd = update_command(install)
    env = _child_env(environ, parent_pid if parent_pid is not None else os.getpid())
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        kwargs["start_new_session"] = True
    popen(cmd, **kwargs)
    return True


def pip_hint(environ: Mapping[str, str]) -> str:
    repo = (environ.get("RESEARCH_CLI_REPO") or DEFAULT_REPO).strip()
    if not _REPO_RE.fullmatch(repo):
        repo = DEFAULT_REPO
    return f'pip install --upgrade "git+https://github.com/{repo}.git"'


def run_self_update(
    *,
    environ: Mapping[str, str],
    transport: Transport | None = None,
    install: Install | None = None,
    current_version: str | None = None,
    timeout: float = EXPLICIT_TIMEOUT,
) -> dict[str, Any]:
    wait_for_parent(environ)
    install = install or current_install()
    version = current_version or __version__
    cleanup_old_binary(install.path)
    if install.kind == "source":
        return {
            "status": "unsupported",
            "kind": "source",
            "version": version,
            "hint": pip_hint(environ),
        }
    if install.path is None:
        raise UpdateError(f"cannot locate {install.kind} install path")
    background = bool((environ.get(WAIT_PID_ENV) or "").strip())
    lock = acquire_update_lock(environ, blocking=not background)
    if lock is None:
        return {
            "status": "busy",
            "kind": install.kind,
            "version": version,
            "path": str(install.path),
        }
    try:
        return _install_latest(
            environ=environ,
            transport=transport,
            install=install,
            version=version,
            timeout=timeout,
        )
    finally:
        lock.close()


def _install_latest(
    *,
    environ: Mapping[str, str],
    transport: Transport | None,
    install: Install,
    version: str,
    timeout: float,
) -> dict[str, Any]:
    release = fetch_latest_release(
        environ=environ, transport=transport, timeout=timeout
    )
    if release is None:
        raise UpdateError("no GitHub release found")
    tag = str(release.get("tag_name") or "")
    if not tag:
        raise UpdateError("github latest release has no tag_name")
    name = asset_name(install.kind, install.system, install.machine)
    asset = choose_asset(release, name)
    size = asset.get("size")
    if isinstance(size, int) and size > MAX_ASSET_BYTES:
        raise UpdateError(f"asset {name} is too large ({size} bytes)")
    data = download_asset(
        str(asset["browser_download_url"]),
        transport=transport,
        timeout=timeout,
    )
    target = install.path
    if target is None:
        raise UpdateError(f"cannot locate {install.kind} install path")
    replace_executable(target, data)
    return {
        "status": "updated",
        "kind": install.kind,
        "from": version,
        "version": tag.lstrip("vV"),
        "tag": tag,
        "path": str(install.path),
        "asset": name,
    }
