"""System telemetry via psutil (already a v4 dependency).

`Telemetry.sample()` is cheap (well under a millisecond on most machines) and
is called about once a second from the GUI thread. Every field degrades to
None when the sensor is not available.
"""
from __future__ import annotations

import os
import time
from collections import deque
from typing import Dict, Optional

try:
    import psutil
except ImportError:          # pragma: no cover - psutil is in requirements.txt
    psutil = None


class Telemetry:
    def __init__(self, history: int = 60):
        self._last_net = None
        self._last_t = None
        self.cpu_history = deque(maxlen=history)
        self.net_down = deque(maxlen=history)
        self.net_up = deque(maxlen=history)
        self._temp_ok = True
        if psutil:
            psutil.cpu_percent(None)
            psutil.cpu_percent(None, percpu=True)

    @staticmethod
    def available() -> bool:
        return psutil is not None

    def _temperature(self) -> Optional[float]:
        if not self._temp_ok or not hasattr(psutil, "sensors_temperatures"):
            return None
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            self._temp_ok = False
            return None
        if not temps:
            self._temp_ok = False
            return None
        for name in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
            entries = temps.get(name)
            if entries:
                package = [e.current for e in entries if "package" in (e.label or "").lower()]
                return float(package[0] if package else max(e.current for e in entries))
        return float(max(e.current for group in temps.values() for e in group))

    def sample(self) -> Dict:
        if psutil is None:
            return {"ok": False}
        now = time.monotonic()
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        cpu = psutil.cpu_percent(None)
        cores = psutil.cpu_percent(None, percpu=True)
        self.cpu_history.append(cpu)

        down = up = 0.0
        try:
            net = psutil.net_io_counters()
            if self._last_net is not None and now > self._last_t:
                dt = now - self._last_t
                down = max(0.0, (net.bytes_recv - self._last_net.bytes_recv) / dt)
                up = max(0.0, (net.bytes_sent - self._last_net.bytes_sent) / dt)
            self._last_net, self._last_t = net, now
        except Exception:
            pass
        self.net_down.append(down)
        self.net_up.append(up)

        battery = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                battery = {"percent": float(b.percent), "plugged": bool(b.power_plugged),
                           "secsleft": b.secsleft if isinstance(b.secsleft, int) and b.secsleft > 0 else None}
        except Exception:
            battery = None
        if battery is None:
            battery = _sysfs_battery()

        try:
            disk = psutil.disk_usage(os.path.expanduser("~"))
            disk_info = {"percent": disk.percent, "free_gb": disk.free / 1e9, "total_gb": disk.total / 1e9}
        except Exception:
            disk_info = None

        try:
            freq = psutil.cpu_freq()
            mhz = freq.current if freq else None
        except Exception:
            mhz = None

        return {
            "ok": True,
            "cpu": cpu,
            "cores": cores,
            "mhz": mhz,
            "ram_percent": vm.percent,
            "ram_used_mb": (vm.total - vm.available) / 2**20,
            "ram_total_mb": vm.total / 2**20,
            "swap_percent": sw.percent if sw.total else None,
            "temp": self._temperature(),
            "battery": battery,
            "disk": disk_info,
            "net_down": down,
            "net_up": up,
            "uptime": time.time() - psutil.boot_time(),
            "procs": len(psutil.pids()),
        }


def _sysfs_battery() -> Optional[Dict]:
    """v4's fallback: read /sys/class/power_supply/BAT0 directly."""
    base = "/sys/class/power_supply/BAT0"
    try:
        with open(os.path.join(base, "capacity")) as f:
            pct = float(f.read().strip())
        status = ""
        try:
            with open(os.path.join(base, "status")) as f:
                status = f.read().strip().lower()
        except OSError:
            pass
        return {"percent": pct, "plugged": status in ("charging", "full", "not charging"), "secsleft": None}
    except (OSError, ValueError):
        return None


def human_rate(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} GB/s"


def human_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h:02d}h"
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def spoken_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    parts = []
    for name, size in (("hour", 3600), ("minute", 60), ("second", 1)):
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n} {name}{'s' if n != 1 else ''}")
    if not parts:
        return "0 seconds"
    return " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]
