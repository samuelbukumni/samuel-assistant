"""Small instruments: arc gauge, segment bar, per-core bars, sparkline."""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QFontMetricsF, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QSizePolicy, QWidget

from samuel.ui.anim import approach
from samuel.ui.paint import glow_arc, glow_path, pen, polar
from samuel.ui.theme import THEME, font

AL = Qt.AlignmentFlag


class Smoothed:
    def __init__(self):
        self.value: Optional[float] = None
        self.shown = 0.0

    def set(self, v):
        self.value = v

    def step(self, dt, speed=6.0) -> bool:
        target = self.value if self.value is not None else 0.0
        old = self.shown
        self.shown = approach(self.shown, target, dt, speed)
        return abs(self.shown - old) > 0.02


class ArcGauge(QWidget):
    START, SPAN = 225.0, -270.0

    def __init__(self, label: str, unit: str = "%", warn: float = 75, crit: float = 90, parent=None):
        super().__init__(parent)
        self.label, self.unit, self.warn, self.crit = label, unit, warn, crit
        self.sub = ""
        self.v = Smoothed()
        self.vmax = 100.0
        self.reveal = 1.0
        self.setMinimumSize(78, 104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(86, 104)

    def set_value(self, v: Optional[float], sub: str = "") -> None:
        self.v.set(v)
        if sub != self.sub:
            self.sub = sub
            self.update()

    def advance(self, dt):
        if self.v.step(dt):
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        cx, cy, r = w / 2, 40, 31
        frac = max(0.0, min(1.0, self.v.shown / self.vmax)) * self.reveal
        val = self.v.value
        col = THEME.level(val, self.warn, self.crit) if val is not None else THEME.c("text_lo")
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        # ticks
        n = 27
        for i in range(n + 1):
            a = self.START + self.SPAN * i / n
            lit = i / n <= frac + 1e-6 and val is not None
            p.setPen(pen(col if lit else THEME.c("primary", 45), 1.2 if i % 3 == 0 else 1))
            r0 = r + (4 if i % 3 == 0 else 5)
            p.drawLine(polar(cx, cy, r0, a), polar(cx, cy, r + 8, a))
        # track
        p.setPen(pen(THEME.c("primary", 34), 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(self.START * 16), int(self.SPAN * 16))
        if val is not None and frac > 0.003:
            glow_arc(p, rect, self.START, self.SPAN * frac, col, 4.0, 1.0)
            end = polar(cx, cy, r, self.START + self.SPAN * frac)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c("text_hi", 240))
            p.drawEllipse(end, 2.2, 2.2)
        # inner hairline
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen(THEME.c("primary", 40), 1))
        p.drawEllipse(QPointF(cx, cy), r - 7, r - 7)
        # number
        num = "--" if val is None else f"{self.v.shown:.0f}"
        nf = font("mono", 19, 600)
        uf = font("mono", 9, 500)
        fm, um = QFontMetricsF(nf), QFontMetricsF(uf)
        unit = "" if val is None else self.unit
        tw = fm.horizontalAdvance(num) + (um.horizontalAdvance(unit) + 1 if unit else 0)
        x0 = cx - tw / 2
        p.setFont(nf)
        p.setPen(THEME.c("text_hi", 245 if val is not None else 120))
        p.drawText(QPointF(x0, cy + fm.capHeight() / 2), num)
        if unit:
            p.setFont(uf)
            p.setPen(THEME.c("text_mid", 220))
            p.drawText(QPointF(x0 + fm.horizontalAdvance(num) + 1, cy + fm.capHeight() / 2), unit)
        p.setFont(font("ui", 11.5, 700, 2.0))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, 76, w, 14), int(AL.AlignHCenter | AL.AlignVCenter), self.label)
        p.setFont(font("mono", 8.5, 500))
        p.setPen(THEME.c("text_lo", 235))
        p.drawText(QRectF(0, 90, w, 12), int(AL.AlignHCenter | AL.AlignVCenter), self.sub)
        p.end()


class SegmentBar(QWidget):
    def __init__(self, label: str, warn: float = 2.0, crit: float = 2.0, invert: bool = False, parent=None):
        super().__init__(parent)
        self.label = label
        self.text = "--"
        self.v = Smoothed()
        self.warn, self.crit, self.invert = warn, crit, invert
        self.charging = False
        self.setFixedHeight(30)

    def set_value(self, frac: Optional[float], text: str, charging: bool = False) -> None:
        self.v.set(None if frac is None else max(0.0, min(1.0, frac)))
        if text != self.text or charging != self.charging:
            self.text, self.charging = text, charging
            self.update()

    def advance(self, dt):
        if self.v.step(dt):
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setFont(font("ui", 11.5, 700, 1.8))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, 0, w, 15), int(AL.AlignLeft | AL.AlignVCenter), self.label)
        p.setFont(font("mono", 10, 500))
        p.setPen(THEME.c("text_hi", 235))
        p.drawText(QRectF(0, 0, w, 15), int(AL.AlignRight | AL.AlignVCenter), self.text)
        n = max(10, int(w / 7))
        seg_w = w / n
        lit = self.v.shown * n if self.v.value is not None else 0
        val = self.v.value
        metric = (1 - val) if (self.invert and val is not None) else val
        col = THEME.level(None if val is None else metric, self.warn, self.crit)
        if self.charging:
            col = THEME.c("ok")
        for i in range(n):
            x = i * seg_w
            r = QRectF(x + 0.5, 19, seg_w - 2.2, 7)
            if i < int(lit):
                p.fillRect(r, col)
            elif i < lit:
                c = col
                c.setAlphaF(lit - int(lit))
                p.fillRect(r, c)
            else:
                p.fillRect(r, THEME.c("primary", 26))
        p.end()


class CoreBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vals = []
        self.shown = []
        self.text = ""
        self.setFixedHeight(54)

    def set_values(self, vals, text: str = ""):
        self.vals = [max(0.0, min(100.0, v)) for v in vals]
        if len(self.shown) != len(self.vals):
            self.shown = [0.0] * len(self.vals)
        self.text = text

    def advance(self, dt):
        changed = False
        for i, v in enumerate(self.vals):
            old = self.shown[i]
            self.shown[i] = approach(old, v, dt, 6)
            changed |= abs(self.shown[i] - old) > 0.05
        if changed:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width()
        p.setFont(font("ui", 11.5, 700, 1.8))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignLeft | AL.AlignVCenter), "CORES")
        p.setFont(font("mono", 10, 500))
        p.setPen(THEME.c("text_hi", 230))
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignRight | AL.AlignVCenter), self.text)
        n = len(self.shown)
        if not n:
            return
        gap = 6
        bw = (w - gap * (n - 1)) / n
        top, h = 19, 20
        for i, v in enumerate(self.shown):
            x = i * (bw + gap)
            rows = 5
            for r in range(rows):
                rr = QRectF(x, top + h - (r + 1) * (h / rows) + 1, bw, h / rows - 1.6)
                lit = v / 100 * rows
                if r < int(lit):
                    p.fillRect(rr, THEME.level(v, 75, 92, 235))
                elif r < lit:
                    p.fillRect(rr, THEME.level(v, 75, 92, 235 * (lit - int(lit))))
                else:
                    p.fillRect(rr, THEME.c("primary", 24))
        p.setFont(font("mono", 8, 500))
        p.setPen(THEME.c("text_lo", 230))
        for i in range(n):
            x = i * (bw + gap)
            p.drawText(QRectF(x, top + h + 1, bw, 10), int(AL.AlignHCenter | AL.AlignVCenter), f"C{i}")
        p.end()


class Sparkline(QWidget):
    def __init__(self, label: str, n: int = 60, parent=None):
        super().__init__(parent)
        self.label = label
        self.a = deque([0.0] * n, maxlen=n)
        self.b = deque([0.0] * n, maxlen=n)
        self.text_a, self.text_b = "--", "--"
        self.setFixedHeight(62)

    def push(self, a: float, b: float, ta: str, tb: str):
        self.a.append(a)
        self.b.append(b)
        self.text_a, self.text_b = ta, tb
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setFont(font("ui", 11.5, 700, 1.8))
        p.setPen(THEME.c("text_mid", 235))
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignLeft | AL.AlignVCenter), self.label)
        p.setFont(font("mono", 9.5, 500))
        fm = QFontMetricsF(p.font())
        tb = f"▲ {self.text_b}"
        ta = f"▼ {self.text_a}"
        p.setPen(THEME.c("accent", 230))
        p.drawText(QRectF(0, 0, w, 14), int(AL.AlignRight | AL.AlignVCenter), tb)
        p.setPen(THEME.c("primary_hi", 230))
        p.drawText(QRectF(0, 0, w - fm.horizontalAdvance(tb) - 12, 14), int(AL.AlignRight | AL.AlignVCenter), ta)
        top, h = 20, self.height() - 22
        # grid
        p.setPen(pen(THEME.c("primary", 22), 1))
        for i in range(1, 4):
            y = top + h * i / 4
            p.drawLine(QPointF(0, y), QPointF(w, y))
        for i in range(1, 6):
            x = w * i / 6
            p.drawLine(QPointF(x, top), QPointF(x, top + h))
        p.setPen(pen(THEME.c("primary", 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0.5, top + 0.5, w - 1, h - 1))
        peak = max(max(self.a), max(self.b), 1024.0)
        scale = math.log1p(peak)
        for series, cname in ((self.b, "accent"), (self.a, "primary_hi")):
            n = len(series)
            path = QPainterPath()
            for i, v in enumerate(series):
                x = w * i / (n - 1)
                y = top + h - 2 - (h - 4) * (math.log1p(v) / scale)
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            fill = QPainterPath(path)
            fill.lineTo(w, top + h)
            fill.lineTo(0, top + h)
            fill.closeSubpath()
            g = QLinearGradient(0, top, 0, top + h)
            g.setColorAt(0, THEME.c(cname, 60))
            g.setColorAt(1, THEME.c(cname, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPath(fill)
            glow_path(p, path, THEME.c(cname, 230), 1.3, 0.7)
        p.end()
