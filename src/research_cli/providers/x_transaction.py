"""x-client-transaction-id (stdlib port of the public web client).

Inputs are on the logged-in homepage: meta twitter-site-verification,
#loading-x-anim-* SVG path data, and webpack `ondemand.s` + ondemand.s.{hash}a.js
KEY_BYTE indices. Algorithm follows iSarabjitDhiman/XClientTransaction (MIT)
and antibot.blog 2025 write-ups. No third-party HTTP libraries.
"""

from __future__ import annotations

import base64
import hashlib
import math
import random
import re
import time
from dataclasses import dataclass

from research_cli.errors import ProviderHttpError

KEYWORD = "obfiowerehiring"
EXTRA_BYTE = 3
TIME_OFFSET = 1682924400
INDICES_RE = re.compile(r"\(\w\[(\d{1,2})\],\s*16\)")
ONDEMAND_INDEX_RE = re.compile(r""",(\d+):["']ondemand\.s["']""")
VERIFICATION_RE = re.compile(
    r'<meta\b[^>]*\bname=["\']twitter-site-verification["\'][^>]*\bcontent=["\']([^"\']+)["\']',
    re.I,
)
VERIFICATION_RE_SWAP = re.compile(
    r'<meta\b[^>]*\bcontent=["\']([^"\']+)["\'][^>]*\bname=["\']twitter-site-verification["\']',
    re.I,
)
FRAME_START = 'id="loading-x-anim-'
FRAME_END = "</svg>"
SECOND_PATH_START = '</path><path d="'


def _fail(message: str) -> None:
    raise ProviderHttpError("x", 0, message)


def extract_verification_key(homepage: str) -> str:
    match = VERIFICATION_RE.search(homepage) or VERIFICATION_RE_SWAP.search(homepage)
    if not match:
        _fail("homepage missing twitter-site-verification")
    return match.group(1)


def extract_ondemand_hash(homepage: str) -> str:
    match = ONDEMAND_INDEX_RE.search(homepage)
    if not match:
        _fail("homepage missing ondemand.s webpack id")
    index = match.group(1)
    hashed = re.search(rf""",{index}:["']([0-9a-f]+)["']""", homepage)
    if not hashed:
        _fail("homepage missing ondemand.s hash")
    return hashed.group(1)


def ondemand_url(hash_hex: str, asset_origin: str) -> str:
    origin = asset_origin.rstrip("/")
    return f"{origin}/responsive-web/client-web/ondemand.s.{hash_hex}a.js"


def extract_main_script_url(homepage: str) -> str | None:
    match = re.search(
        r"""src=["'](https://abs\.twimg\.com/responsive-web/client-web/main\.[^"']+)["']""",
        homepage,
    )
    if match:
        return match.group(1)
    match = re.search(
        r"""src=["'](/responsive-web/client-web/main\.[^"']+)["']""",
        homepage,
    )
    return match.group(1) if match else None


def extract_indices(ondemand_js: str) -> list[int]:
    found = [int(item) for item in INDICES_RE.findall(ondemand_js)]
    if len(found) < 2:
        _fail("ondemand.s.js missing KEY_BYTE indices")
    return found


def extract_frames(homepage: str) -> list[str]:
    frames: list[str] = []
    start = 0
    while True:
        pos = homepage.find(FRAME_START, start)
        if pos < 0:
            break
        end = homepage.find(FRAME_END, pos)
        if end < 0:
            break
        frames.append(homepage[pos + len(FRAME_START) : end])
        start = end + len(FRAME_END)
    if len(frames) < 4:
        _fail("homepage missing loading-x-anim SVG frames")
    return frames[:4]


def _round_js(num: float) -> int:
    floor = math.floor(num)
    return floor if (num - floor) < 0.5 else math.ceil(num)


def _is_odd(num: int) -> float:
    return -1.0 if num % 2 else 0.0


def _scale(value: float, value_min: float, value_max: float, rounding: bool) -> float:
    result = value * (value_max - value_min) / 255.0 + value_min
    return float(math.floor(result)) if rounding else round(result, 2)


def _cubic_calculate(a: float, b: float, m: float) -> float:
    m1 = 1.0 - m
    return 3.0 * a * m1 * m1 * m + 3.0 * b * m1 * m * m + m * m * m


def _cubic_value(curve: list[float], t: float) -> float:
    if t <= 0.0:
        if curve[0] > 0.0:
            value = curve[1] / curve[0]
        elif curve[1] == 0.0 and curve[2] > 0.0:
            value = curve[3] / curve[2]
        else:
            value = 0.0
        return value * t
    if t >= 1.0:
        if curve[2] < 1.0:
            value = (curve[3] - 1.0) / (curve[2] - 1.0)
        elif curve[2] == 1.0 and curve[0] < 1.0:
            value = (curve[1] - 1.0) / (curve[0] - 1.0)
        else:
            value = 0.0
        return 1.0 + value * (t - 1.0)
    start = 0.0
    end = 1.0
    mid = 0.0
    while start < end:
        mid = (start + end) / 2.0
        est = _cubic_calculate(curve[0], curve[2], mid)
        if abs(t - est) < 0.00001:
            return _cubic_calculate(curve[1], curve[3], mid)
        if est < t:
            start = mid
        else:
            end = mid
    return _cubic_calculate(curve[1], curve[3], mid)  # pragma: no cover


def _float_to_hex(numf: float) -> str:
    numi = int(numf)
    fraction = numf - numi
    if not fraction:
        return hex(numi)[2:]
    result = ["."]
    guard = 0
    while fraction > 0.0 and guard < 24:
        fraction *= 16.0
        integer = int(fraction)
        fraction -= integer
        result.append(chr(integer + 87) if integer > 9 else str(integer))
        guard += 1
    return hex(numi)[2:] + "".join(result)


def _generate_2d_array(frame: str) -> list[list[int]]:
    pos = frame.find(SECOND_PATH_START)
    if pos < 0:
        _fail("loading-x-anim frame missing second path")
    start = pos + len(SECOND_PATH_START)
    end = frame.find('"', start)
    d_attr = frame[start:end] if end >= 0 else frame[start:]
    split = re.compile(r"[^\d]+").split
    rows: list[list[int]] = []
    for path in d_attr[9:].split("C"):
        nums = [int(item) for item in split(path) if item]
        if nums:
            rows.append(nums)
    if not rows:
        _fail("loading-x-anim path produced no animation rows")
    return rows


def animate(frames: list[int], target_time: float) -> str:
    curve = [
        _scale(float(item), _is_odd(index), 1.0, False)
        for index, item in enumerate(frames[7:])
    ]
    if len(curve) < 4:
        _fail("animation frame too short for cubic bezier")
    cubic = _cubic_value(curve[:4], target_time)
    color_a = (float(frames[0]), float(frames[1]), float(frames[2]))
    color_b = (float(frames[3]), float(frames[4]), float(frames[5]))
    color = [
        max(0.0, min(255.0, a * (1.0 - cubic) + b * cubic))
        for a, b in zip(color_a, color_b)
    ]
    rotation_b = _scale(float(frames[6]), 60.0, 360.0, True)
    rotation = 0.0 * (1.0 - cubic) + rotation_b * cubic
    rad = math.radians(rotation)
    matrix = (math.cos(rad), -math.sin(rad), math.sin(rad), math.cos(rad))
    parts = [
        hex(round(color[0]))[2:],
        hex(round(color[1]))[2:],
        hex(round(color[2]))[2:],
    ]
    for value in matrix:
        hex_value = _float_to_hex(abs(round(value, 2)))
        if hex_value.startswith("."):
            hex_value = "0" + hex_value
        parts.append(hex_value or "0")
    parts.extend(["0", "0"])
    return "".join(parts).replace(".", "").replace("-", "")


def calculate_animation_key(
    frames: list[str],
    row_index: int,
    key_bytes: bytes,
    key_bytes_indices: list[int],
    total_time: int = 4096,
) -> str:
    if len(key_bytes) <= 5:
        _fail("twitter-site-verification key too short")
    frame = frames[key_bytes[5] % 4]
    array = _generate_2d_array(frame)
    if row_index >= len(key_bytes):
        _fail("KEY_BYTE row index out of range")
    chosen = array[key_bytes[row_index] % 16]
    frame_time = 1
    for index in key_bytes_indices:
        if index >= len(key_bytes):
            _fail("KEY_BYTE index out of range")
        frame_time *= key_bytes[index] % 16
    frame_time = _round_js(frame_time / 10) * 10
    return animate(chosen, frame_time / total_time)


@dataclass(frozen=True)
class ClientTransaction:
    key_bytes: bytes
    animation_key: str
    keyword: str = KEYWORD
    extra: int = EXTRA_BYTE

    @classmethod
    def from_documents(cls, homepage: str, ondemand_js: str) -> ClientTransaction:
        key = extract_verification_key(homepage)
        try:
            key_bytes = base64.b64decode(key)
        except Exception as exc:
            raise ProviderHttpError("x", 0, "invalid twitter-site-verification") from exc
        indices = extract_indices(ondemand_js)
        frames = extract_frames(homepage)
        animation_key = calculate_animation_key(
            frames, indices[0], key_bytes, indices[1:]
        )
        return cls(key_bytes=key_bytes, animation_key=animation_key)

    def generate_transaction_id(
        self,
        method: str,
        path: str,
        *,
        time_now: int | None = None,
        random_num: int | None = None,
    ) -> str:
        now = time_now
        if now is None:
            now = math.floor((time.time() * 1000 - TIME_OFFSET * 1000) / 1000)
        time_bytes = bytes((now >> (8 * i)) & 0xFF for i in range(4))
        payload = f"{method}!{path}!{now}{self.keyword}{self.animation_key}"
        digest = hashlib.sha256(payload.encode("utf-8")).digest()[:16]
        nonce = random.randint(0, 255) if random_num is None else random_num & 0xFF
        raw = bytes([nonce]) + bytes(
            b ^ nonce
            for b in (
                *self.key_bytes,
                *time_bytes,
                *digest,
                self.extra,
            )
        )
        return base64.b64encode(raw).decode("ascii").rstrip("=")
