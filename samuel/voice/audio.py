"""Small pure-Python audio helpers (no numpy, no audioop).

Python 3.13 removed `audioop`, which v4 used, so these replace it.
"""
from __future__ import annotations

import array
import math
import sys


def _samples(data: bytes) -> array.array:
    a = array.array("h")
    a.frombytes(data[: len(data) - (len(data) % 2)])
    if sys.byteorder == "big":
        a.byteswap()
    return a


def rms(data: bytes) -> float:
    """Root mean square of 16-bit little-endian mono PCM."""
    a = _samples(data)
    if not a:
        return 0.0
    step = max(1, len(a) // 1024)          # subsample: plenty for a level meter
    picked = a[::step]
    return math.sqrt(sum(s * s for s in picked) / len(picked))


def level(data: bytes, full_scale: float = 6000.0) -> float:
    """RMS mapped to 0..1 with a gentle curve, for the HUD visualiser."""
    return max(0.0, min(1.0, (rms(data) / full_scale) ** 0.7))


def resample(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear-interpolation resampler for 16-bit mono PCM (e.g. 44100 -> 16000)."""
    if src_rate == dst_rate:
        return data
    a = _samples(data)
    n = len(a)
    if n == 0:
        return b""
    out_len = int(n * dst_rate / src_rate)
    ratio = src_rate / dst_rate
    out = array.array("h", bytes(2 * out_len))
    last = n - 1
    for i in range(out_len):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        s0 = a[j]
        s1 = a[j + 1] if j < last else s0
        out[i] = int(s0 + (s1 - s0) * frac)
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()
