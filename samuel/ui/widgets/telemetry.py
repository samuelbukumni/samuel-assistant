"""Left column: system telemetry and the environment/schedule panel."""
from __future__ import annotations

import socket
import time
from typing import Dict, List

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from samuel.core.telemetry import human_duration, human_rate
from samuel.ui.paint import pen, wrap
from samuel.ui.theme import THEME, font
from samuel.ui.widgets.gauges import ArcGauge, CoreBars, SegmentBar, Sparkline
from samuel.ui.widgets.panel import Panel

AL = Qt.AlignmentFlag


class FooterLine(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List = []
        self.setFixedHeight(16)

    def set_items(self, items):
        if items != self.items:
            self.items = items
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width()
        p.setPen(pen(THEME.c("primary", 40), 1))
        p.drawLine(0, 0, w, 0)
        n = len(self.items)
        for i, (k, v) in enumerate(self.items):
            r = QRectF(w * i / n, 3, w / n, 13)
            p.setFont(font("ui", 10.5, 700, 1.4))
            p.setPen(THEME.c("text_lo", 255))
            fm = QFontMetricsF(p.font())
            kw = fm.horizontalAdvance(k + " ")
            align = AL.AlignLeft if i == 0 else AL.AlignRight if i == n - 1 else AL.AlignHCenter
            vf = font("mono", 9.5, 500)
            vw = QFontMetricsF(vf).horizontalAdvance(v)
            total = kw + vw
            x = r.x() if align == AL.AlignLeft else r.right() - total if align == AL.AlignRight else r.center().x() - total / 2
            p.drawText(QRectF(x, r.y(), kw, r.height()), int(AL.AlignLeft | AL.AlignVCenter), k)
            p.setFont(vf)
            p.setPen(THEME.c("text_hi", 225))
            p.drawText(QRectF(x + kw, r.y(), vw + 2, r.height()), int(AL.AlignLeft | AL.AlignVCenter), v)
        p.end()


class TopProcs(QWidget):
    """The heaviest processes by memory — the usual answer to 'why is my laptop slow?'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[Dict] = []
        self.setMinimumHeight(0)
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_rows(self, rows):
        self.rows = rows
        self.update()

    def paintEvent(self, _):
        if self.height() < 40 or not self.rows:
            return
        p = QPainter(self)
        w = self.width()
        p.setFont(font("ui", 11.5, 700, 1.8))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignLeft | AL.AlignVCenter), "TOP PROCESSES")
        p.setFont(font("mono", 8.5, 500))
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(0, 0, w - 70, 14), int(AL.AlignRight | AL.AlignVCenter), "CPU")
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignRight | AL.AlignVCenter), "MEMORY")
        top = max((r["mem_mb"] for r in self.rows), default=1) or 1
        y = 20
        for r in self.rows[: max(0, int((self.height() - 20) // 19))]:
            frac = r["mem_mb"] / top
            p.fillRect(QRectF(0, y + 15, w * frac, 1.5), THEME.c("primary", 120))
            p.fillRect(QRectF(w * frac, y + 15, w * (1 - frac), 1.5), THEME.c("primary", 22))
            p.setFont(font("mono", 10, 500))
            p.setPen(THEME.c("text_hi", 230))
            name = r["name"][:22]
            p.drawText(QRectF(0, y, w - 120, 15), int(AL.AlignLeft | AL.AlignVCenter), name)
            p.setPen(THEME.c("text_mid", 230))
            p.drawText(QRectF(0, y, w - 70, 15), int(AL.AlignRight | AL.AlignVCenter), f"{r['cpu']:.0f}%")
            p.setPen(THEME.c("text_hi", 230))
            mem = f"{r['mem_mb'] / 1024:.1f} GB" if r["mem_mb"] >= 1024 else f"{r['mem_mb']:.0f} MB"
            p.drawText(QRectF(0, y, w, 15), int(AL.AlignRight | AL.AlignVCenter), mem)
            y += 19
        p.end()


class TelemetryPanel(Panel):
    def __init__(self, parent=None):
        super().__init__("01", "SYSTEM TELEMETRY", socket.gethostname().upper()[:12], parent)
        row = QHBoxLayout()
        row.setSpacing(2)
        self.cpu = ArcGauge("CPU", "%", 70, 90)
        self.ram = ArcGauge("MEMORY", "%", 75, 90)
        self.temp = ArcGauge("THERMAL", "°", 70, 85)
        for g in (self.cpu, self.ram, self.temp):
            row.addWidget(g)
        self.body.addLayout(row)
        self.cores = CoreBars()
        self.body.addWidget(self.cores)
        self.power = SegmentBar("POWER", invert=True, warn=0.75, crit=0.88)
        self.disk = SegmentBar("STORAGE", warn=0.80, crit=0.92)
        self.swap = SegmentBar("SWAP", warn=0.5, crit=0.8)
        for b in (self.power, self.disk, self.swap):
            self.body.addWidget(b)
        self.net = Sparkline("NETWORK")
        self.body.addWidget(self.net)
        self.footer = FooterLine()
        self.body.addWidget(self.footer)
        self.procs = TopProcs()
        self.body.addWidget(self.procs, 1)
        self.instruments = [self.cpu, self.ram, self.temp, self.cores, self.power, self.disk, self.swap]

    def advance(self, dt):
        for w in self.instruments:
            w.advance(dt)

    def update_sample(self, s: Dict) -> None:
        if not s.get("ok"):
            return
        self.set_led(True)
        cores = s.get("cores") or []
        self.cpu.set_value(s["cpu"], f"{len(cores)} CORES")
        self.ram.set_value(s["ram_percent"], f"{s['ram_used_mb'] / 1024:.1f}/{s['ram_total_mb'] / 1024:.1f} GB")
        t = s.get("temp")
        self.temp.set_value(t, "PACKAGE" if t is not None else "NO SENSOR")
        self.temp.vmax = 100
        self.cores.set_values(cores, f"{s['mhz'] / 1000:.2f} GHz" if s.get("mhz") else "")
        b = s.get("battery")
        if b:
            left = ""
            if b.get("plugged"):
                left = "AC · CHARGING" if b["percent"] < 99 else "AC · FULL"
            elif b.get("secsleft"):
                left = human_duration(b["secsleft"]) + " LEFT"
            self.power.set_value(b["percent"] / 100, f"{b['percent']:.0f}%  {left}".strip(), bool(b.get("plugged")))
        else:
            self.power.set_value(None, "NO BATTERY · AC")
        d = s.get("disk")
        if d:
            self.disk.set_value(d["percent"] / 100, f"{d['free_gb']:.0f} GB FREE")
        sw = s.get("swap_percent")
        self.swap.set_value(None if sw is None else sw / 100, "--" if sw is None else f"{sw:.0f}%")
        self.net.push(s.get("net_down", 0.0), s.get("net_up", 0.0), human_rate(s.get("net_down", 0.0)),
                      human_rate(s.get("net_up", 0.0)))
        self.footer.set_items([("UPTIME", human_duration(s["uptime"])), ("PROCS", str(s["procs"])),
                               ("LOAD", f"{s['cpu']:.0f}%")])


class OpsView(QWidget):
    """Weather block + the next reminders with live countdowns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.weather: Dict = {"ok": False, "reason": "not configured"}
        self.reminders: List[Dict] = []
        self.setFixedHeight(166)

    def set_weather(self, w: Dict):
        self.weather = w or {"ok": False}
        self.update()

    def set_reminders(self, items: List[Dict]):
        self.reminders = items or []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        y = 0
        wx = self.weather
        if wx.get("ok"):
            p.setFont(font("mono", 30, 400))
            p.setPen(THEME.c("text_hi", 250))
            tf = QFontMetricsF(p.font())
            temp = f"{round(wx['temp'])}"
            p.drawText(QRectF(0, y, 90, 36), int(AL.AlignLeft | AL.AlignVCenter), temp)
            tw = tf.horizontalAdvance(temp)
            p.setFont(font("mono", 13, 500))
            p.setPen(THEME.c("primary_hi", 230))
            p.drawText(QRectF(tw + 2, y + 2, 30, 18), int(AL.AlignLeft | AL.AlignVCenter), "°C")
            x = max(86.0, tw + 34)
            p.setFont(font("ui", 15, 700, 1.0))
            p.setPen(THEME.c("text_hi", 240))
            p.drawText(QRectF(x, y + 1, w - x, 18), int(AL.AlignLeft | AL.AlignVCenter), wx["text"].upper())
            p.setFont(font("ui", 12, 600, 1.0))
            p.setPen(THEME.c("text_mid", 235))
            place = wx["place"].upper() + ("  · CACHED" if wx.get("stale") else "")
            p.drawText(QRectF(x, y + 19, w - x, 16), int(AL.AlignLeft | AL.AlignVCenter), place)
            y += 42
            stats = [("HI/LO", f"{round(wx['high'])}°/{round(wx['low'])}°" if wx.get("high") is not None else "--"),
                     ("FEELS", f"{round(wx['feels'])}°" if wx.get("feels") is not None else "--"),
                     ("HUM", f"{round(wx['humidity'])}%" if wx.get("humidity") is not None else "--"),
                     ("WIND", f"{round(wx['wind'])} km/h" if wx.get("wind") is not None else "--")]
            cw = w / 4
            for i, (k, v) in enumerate(stats):
                p.setFont(font("ui", 10.5, 700, 1.4))
                p.setPen(THEME.c("text_lo", 255))
                p.drawText(QRectF(i * cw, y, cw, 13), int(AL.AlignLeft | AL.AlignVCenter), k)
                p.setFont(font("mono", 10.5, 500))
                p.setPen(THEME.c("text_hi", 230))
                p.drawText(QRectF(i * cw, y + 13, cw, 15), int(AL.AlignLeft | AL.AlignVCenter), v)
            y += 34
        else:
            p.setFont(font("ui", 12, 700, 1.6))
            p.setPen(THEME.c("text_lo", 255))
            reason = wx.get("reason", "")
            msg = "WEATHER · SET weather_city IN CONFIG" if reason == "not configured" else "WEATHER · LINK UNAVAILABLE"
            p.drawText(QRectF(0, y, w, 18), int(AL.AlignLeft | AL.AlignVCenter), msg)
            y += 26

        p.setPen(pen(THEME.c("primary", 40), 1))
        p.drawLine(0, int(y), w, int(y))
        y += 8
        p.setFont(font("ui", 11.5, 700, 1.8))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, y, w, 14), int(AL.AlignLeft | AL.AlignVCenter), "TIMERS & REMINDERS")
        p.setFont(font("mono", 9.5, 500))
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(0, y, w, 14), int(AL.AlignRight | AL.AlignVCenter), f"{len(self.reminders):02d} ACTIVE")
        y += 20
        now = time.time()
        if not self.reminders:
            p.setFont(font("ui", 12.5, 500))
            p.setPen(THEME.c("text_lo", 255))
            p.drawText(QRectF(0, y, w, 16), int(AL.AlignLeft | AL.AlignVCenter), "Nothing scheduled  ·  “remind me in 20 minutes to stretch”")
        for r in self.reminders[: max(1, int((self.height() - y) // 22))]:
            left = max(0, int(r["due"] - now))
            h, rem = divmod(left, 3600)
            m, sec = divmod(rem, 60)
            cd = f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
            soon = left < 60
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c("accent" if soon else "primary", 230))
            p.drawRect(QRectF(0, y + 5, 3, 10))
            p.setFont(font("mono", 12, 600))
            p.setPen(THEME.c("accent" if soon else "text_hi", 245))
            p.drawText(QRectF(10, y, 70, 20), int(AL.AlignLeft | AL.AlignVCenter), cd)
            p.setFont(font("ui", 13, 600))
            p.setPen(THEME.c("text_mid", 240))
            tag = "TIMER" if r.get("kind") == "timer" else "REMIND"
            text = wrap(QFontMetricsF(p.font()), r["text"], w - 140, 1)
            p.drawText(QRectF(82, y, w - 140, 20), int(AL.AlignLeft | AL.AlignVCenter), text[0] if text else "")
            p.setFont(font("mono", 8.5, 500))
            p.setPen(THEME.c("text_lo", 255))
            p.drawText(QRectF(0, y, w, 20), int(AL.AlignRight | AL.AlignVCenter), tag)
            y += 22
        p.end()


class OpsPanel(Panel):
    def __init__(self, parent=None):
        super().__init__("02", "ENVIRONMENT", "OPEN-METEO", parent)
        self.view = OpsView()
        self.body.addWidget(self.view)

    def tick_second(self):
        if self.view.reminders:
            self.view.update()
