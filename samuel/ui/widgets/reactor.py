"""The central reactor: an arc-reactor core inside a rotating HUD reticle.

States and what changes:
  idle       slow rotation, soft breathing core, faint radar sweep
  listening  ripples travel outwards, waveform follows mic level, rings brighten
  thinking   rings spin faster, three orbiting tracers, core flickers
  speaking   waveform and core are driven by the real TTS loudness
  alert      accent colour pulses (reminders)

Everything is drawn with QPainter. Static parts (tick ring, labels, hairlines)
are cached in a pixmap and rebuilt only on resize or theme change.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

from PyQt6.QtCore import QLineF, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFontMetricsF, QPainter, QPainterPath,
                         QPixmap, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from samuel.ui.anim import approach, ease_in_out_cubic, ease_out_cubic, ease_out_expo, segment
from samuel.ui.paint import glow_arc, glow_path, pen, polar
from samuel.ui.theme import THEME, font

STATES = {
    #            spin  sweep  wave  core  ring
    "idle":      (1.0, 0.55, 0.10, 0.55, 0.55),
    "listening": (1.6, 0.30, 0.45, 0.80, 0.95),
    "thinking":  (4.2, 0.90, 0.20, 0.70, 0.85),
    "speaking":  (1.4, 0.25, 1.00, 1.00, 0.85),
    "alert":     (2.0, 0.60, 0.40, 0.95, 1.00),
}
LABELS = {"idle": "STANDING BY", "listening": "LISTENING", "thinking": "PROCESSING",
          "speaking": "SPEAKING", "alert": "ALERT", "boot": "INITIALISING"}

N_BARS = 112
GAP = 22.0   # degrees kept clear at top and bottom for the labels


class Reactor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(380, 360)
        self.state = "idle"
        self.callsign = "J.A.R.V.I.S."
        self.callouts: List[Tuple[str, str]] = [("", "")] * 4
        self.boot = 1.0                 # 0..1 ignition progress
        self.lite = False               # skip the radar sweep (slow machines)
        self.t = 0.0
        self._p = list(STATES["idle"])  # smoothed state parameters
        self._alert = 0.0
        self._energy_in = 0.0
        self._energy = 0.0
        self._bars = [0.0] * N_BARS
        self._phase = [random.random() * 6.28 for _ in range(N_BARS)]
        self._rot = [0.0, 0.0, 0.0, 0.0]
        self._sweep = 90.0
        self._ripples: List[float] = []
        self._ripple_clock = 0.0
        self._cache: QPixmap | None = None
        self._cache_key = None
        self._bar_angles = self._make_bar_angles()
        THEME.changed.connect(self._invalidate)

    def sizeHint(self) -> QSize:
        return QSize(640, 520)

    # ------------------------------------------------------------------ state
    def set_state(self, state: str) -> None:
        if state in STATES:
            self.state = state

    def set_energy(self, value: float) -> None:
        self._energy_in = max(0.0, min(1.0, float(value)))

    def set_callsign(self, s: str) -> None:
        self.callsign = s
        self._invalidate()

    def set_callouts(self, items: List[Tuple[str, str]]) -> None:
        self.callouts = (list(items) + [("", "")] * 4)[:4]

    def _invalidate(self) -> None:
        self._cache_key = None

    @staticmethod
    def _make_bar_angles() -> List[float]:
        half = N_BARS // 2
        span = 180 - 2 * GAP - 4
        out = []
        for start in (90 + GAP + 2, 270 + GAP + 2):
            out += [start + span * (i + 0.5) / half for i in range(half)]
        return out

    # ------------------------------------------------------------------- tick
    def advance(self, dt: float) -> None:
        self.t += dt
        target = STATES.get(self.state, STATES["idle"])
        for i in range(5):
            self._p[i] = approach(self._p[i], target[i], dt, 3.5)
        self._alert = approach(self._alert, 1.0 if self.state == "alert" else 0.0, dt, 4.0)

        e_in = self._energy_in
        if self.state == "thinking":
            e_in = max(e_in, 0.12 + 0.08 * math.sin(self.t * 9))
        if self.state == "idle":
            e_in = max(e_in, 0.05 + 0.03 * math.sin(self.t * 1.3))
        speed = 22.0 if e_in > self._energy else 6.0     # fast attack, slow release
        self._energy = approach(self._energy, e_in, dt, speed)

        spin = self._p[0]
        self._rot[0] += dt * 9 * spin
        self._rot[1] -= dt * 14 * spin
        self._rot[2] += dt * 5 * spin
        self._rot[3] -= dt * 30 * spin
        self._sweep -= dt * 70 * (0.6 + 0.4 * spin)

        gain = self._p[2]
        t = self.t
        for i in range(N_BARS):
            ph = self._phase[i]
            n = (0.5 + 0.5 * math.sin(t * 7.1 + ph * 3)) * (0.55 + 0.45 * math.sin(t * 2.3 + i * 0.37))
            shape = 0.65 + 0.35 * math.sin(i * 0.21 + t * 1.7)
            target_v = min(1.0, 1.5 * self._energy * gain * (0.3 + 0.7 * n) * shape)
            self._bars[i] = approach(self._bars[i], target_v, dt, 18 if target_v > self._bars[i] else 7)

        if self.state == "listening":
            self._ripple_clock += dt
            if self._ripple_clock > 0.7 or not self._ripples:
                self._ripple_clock = 0.0
                self._ripples.append(0.0)
        self._ripples = [r for r in (r + dt / 2.2 for r in self._ripples) if r < 1.0]
        self.update()

    # ------------------------------------------------------------------ paint
    def _geometry(self):
        w, h = self.width(), self.height()
        side = min(w, h)
        R = side / 2 - 10
        return w / 2, h / 2, R

    def _static_layer(self, cx, cy, R) -> QPixmap:
        with_ring = self.boot >= 1.0
        key = (self.width(), self.height(), THEME.version, self.callsign, round(self.devicePixelRatioF(), 2), with_ring)
        if self._cache is not None and self._cache_key == key:
            return self._cache
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ambient disc
        g = QRadialGradient(QPointF(cx, cy), R * 1.05)
        g.setColorAt(0.0, THEME.c("primary", 26))
        g.setColorAt(0.45, THEME.c("primary", 12))
        g.setColorAt(1.0, THEME.c("primary", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), R * 1.05, R * 1.05)

        # outer hairlines
        for rr, a in ((0.995, 70), (0.925, 40), (0.79, 34), (0.565, 30), (0.335, 55)):
            p.setPen(pen(THEME.c("primary", a), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), R * rr, R * rr)

        # compass tick ring
        for i in range(0, 360, 2):
            major = i % 10 == 0
            r0 = R * (0.935 if major else 0.955)
            col = THEME.c("primary", 120 if major else 48)
            p.setPen(pen(col, 1.2 if major else 1))
            p.drawLine(polar(cx, cy, r0, i), polar(cx, cy, R * 0.975, i))
        f = font("mono", max(7.5, R * 0.032), 500)
        p.setFont(f)
        fm = QFontMetricsF(f)
        p.setPen(THEME.c("text_lo", 200))
        for i in range(0, 360, 30):
            if i in (0, 90, 180, 270):
                continue
            label = f"{(90 - i) % 360:03d}"
            pt = polar(cx, cy, R * 0.903, i)
            p.drawText(QPointF(pt.x() - fm.horizontalAdvance(label) / 2, pt.y() + fm.capHeight() / 2), label)

        # cardinal brackets just outside the disc
        for a in (0, 90, 180, 270):
            p.setPen(pen(THEME.c("primary", 170), 1.4))
            p.drawLine(polar(cx, cy, R * 1.005, a - 2.2), polar(cx, cy, R * 1.005, a + 2.2))

        # label plates in the top and bottom gaps
        p.setPen(pen(THEME.c("primary", 60), 1))
        for a0 in (90, 270):
            for side in (-1, 1):
                p.drawLine(polar(cx, cy, R * 0.60, a0 + side * GAP), polar(cx, cy, R * 0.775, a0 + side * GAP))

        if with_ring:
            self._paint_ring_a(p, cx, cy, R, 1.0, THEME.c("primary"))

        # callsign in the top gap
        cf = font("display", max(9, R * 0.045), 700, max(1.5, R * 0.012))
        p.setFont(cf)
        p.setPen(THEME.c("text_hi", 225))
        fm = QFontMetricsF(cf)
        tw = fm.horizontalAdvance(self.callsign)
        p.drawText(QPointF(cx - tw / 2, cy - R * 0.665 + fm.capHeight() / 2), self.callsign)
        p.end()
        self._cache, self._cache_key = pm, key
        return pm

    def paintEvent(self, _ev) -> None:
        cx, cy, R = self._geometry()
        if R < 40:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        boot = self.boot
        b_static = ease_out_cubic(segment(boot, 0.25, 0.75))
        b_ring = ease_out_expo(segment(boot, 0.0, 0.55))
        b_core = ease_in_out_cubic(segment(boot, 0.45, 1.0))
        spin, sweep_a, _, core_a, ring_a = self._p
        primary = THEME.mix("primary", "accent", self._alert * (0.5 + 0.5 * math.sin(self.t * 7)))

        # 1. static layer (fades in during boot)
        if b_static > 0:
            p.setOpacity(b_static)
            p.drawPixmap(0, 0, self._static_layer(cx, cy, R))
            p.setOpacity(1.0)

        # boot: outer ring draws itself in
        if boot < 1.0:
            rect = QRectF(cx - R * 0.995, cy - R * 0.995, R * 1.99, R * 1.99)
            glow_arc(p, rect, 90, -360 * b_ring, THEME.c("primary_hi", 230), 2.0, 1.2)

        # 2. radar sweep in the outer annulus
        if b_static > 0.3 and not self.lite:
            self._paint_sweep(p, cx, cy, R, sweep_a * b_static, primary)

        # 3. listening ripples
        for r in self._ripples:
            rr = R * (0.34 + 0.6 * ease_out_cubic(r))
            p.setPen(pen(THEME.c("primary_hi", 230 * max(0.0, 1 - r) ** 1.3), 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rr, rr)

        # 4. segmented ring A (fixed, with gaps for the labels) at 0.86R. It lives in the static
        #    cache once booted; during boot and alerts it is drawn live so it can fade and tint.
        if b_ring > 0:
            if boot < 1.0 or self._alert > 0.02:
                self._paint_ring_a(p, cx, cy, R, ring_a * b_ring if boot >= 1 else b_ring, primary)
            self._paint_ring_highlight(p, cx, cy, R, ring_a * b_ring)

        # 5. dashed ring B rotating, with bright brackets, at 0.80R
        if b_static > 0:
            rB = R * 0.815
            dpen = pen(THEME.c("primary", 85 * b_static), 2.2)
            dpen.setDashPattern([1.2, 3.2])
            p.setPen(dpen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.save()
            p.translate(cx, cy)
            p.rotate(self._rot[1])
            p.drawEllipse(QPointF(0, 0), rB, rB)
            p.restore()
            rect = QRectF(cx - rB, cy - rB, rB * 2, rB * 2)
            for k in range(4):
                glow_arc(p, rect, -self._rot[1] + k * 90 + 20, 9, THEME.c("primary_hi", 230 * b_static * ring_a), 2.2, 0.9)

        # 6. voice waveform ring (bars outward from 0.60R)
        if b_core > 0:
            self._paint_wave(p, cx, cy, R, b_core, primary)

        # 7. reactor coils — drawn once into a pixmap, then rotated; energy only changes opacity
        if b_core > 0:
            pm = self._coil_layer(R)
            half = pm.width() / pm.devicePixelRatio() / 2
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(cx, cy)
            p.rotate(-self._rot[2])
            p.setOpacity(b_core * (0.72 + 0.28 * min(1.0, self._energy * 1.6)))
            p.drawPixmap(QPointF(-half, -half), pm)
            p.restore()
            self._paint_coil_ticks(p, cx, cy, R, b_core)

        # 8. thinking tracers
        if self.state == "thinking" or self._p[0] > 1.8:
            k = min(1.0, (self._p[0] - 1.0) / 3.0)
            rT = R * 0.70
            for i in range(3):
                base = self._rot[3] * 6 + i * 120
                for j in range(10):
                    a = base - j * 3.2
                    pt = polar(cx, cy, rT, a)
                    alpha = 230 * k * (1 - j / 10) ** 2
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(THEME.c("primary_hi", alpha))
                    p.drawEllipse(pt, 2.6 - j * 0.18, 2.6 - j * 0.18)

        # 9. core
        if b_core > 0:
            self._paint_core(p, cx, cy, R, b_core * (0.55 + 0.45 * core_a), primary)

        # 10. state label in the bottom gap
        label = "INITIALISING" if boot < 1 else LABELS.get(self.state, "")
        lf = font("ui", max(10, R * 0.05), 700, max(2, R * 0.016))
        p.setFont(lf)
        fm = QFontMetricsF(lf)
        tw = fm.horizontalAdvance(label)
        ly = cy + R * 0.69
        blink = 0.75 + 0.25 * math.sin(self.t * (6 if self.state != "idle" else 2))
        p.setPen(THEME.c("primary_hi" if self.state != "idle" else "text_mid", 255 * blink * max(b_static, 0.4)))
        p.drawText(QPointF(cx - tw / 2, ly + fm.capHeight() / 2), label)
        # little indicator squares either side of label
        for s in (-1, 1):
            x = cx + s * (tw / 2 + 12)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c("primary", 200 * blink))
            p.drawRect(QRectF(x - 2, ly - 2, 4, 4))

        # 11. data callouts at the diagonals
        if b_static > 0.5:
            self._paint_callouts(p, cx, cy, R, ease_out_cubic(segment(boot, 0.6, 1.0)))
        p.end()

    def _paint_sweep(self, p, cx, cy, R, strength, color) -> None:
        if strength <= 0.02:
            return
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addEllipse(QPointF(cx, cy), R * 0.92, R * 0.92)
        path.addEllipse(QPointF(cx, cy), R * 0.57, R * 0.57)
        g = QConicalGradient(QPointF(cx, cy), self._sweep % 360)
        c0, c1, c2 = QColor(color), QColor(color), QColor(color)
        c0.setAlpha(int(70 * strength))
        c1.setAlpha(int(14 * strength))
        c2.setAlpha(0)
        g.setColorAt(0.0, c0)
        g.setColorAt(0.09, c1)
        g.setColorAt(0.22, c2)
        g.setColorAt(1.0, c2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(path)
        # leading edge
        a = self._sweep % 360
        p.setPen(pen(THEME.c("primary_hi", 120 * strength), 1.2))
        p.drawLine(polar(cx, cy, R * 0.57, a), polar(cx, cy, R * 0.92, a))

    def _paint_ring_highlight(self, p, cx, cy, R, strength) -> None:
        rI = R * 0.84
        rect2 = QRectF(cx - rI, cy - rI, rI * 2, rI * 2)
        hl = (self._rot[0] * 2) % 360
        if not (90 - GAP - 8 < hl < 90 + GAP) and not (270 - GAP - 8 < hl < 270 + GAP):
            glow_arc(p, rect2, hl, 8, THEME.c("primary_hi", 220 * strength), 1.6)

    def _paint_ring_a(self, p, cx, cy, R, strength, color) -> None:
        rA = R * 0.86
        rect = QRectF(cx - rA, cy - rA, rA * 2, rA * 2)
        c = QColor(color)
        c.setAlpha(int(235 * strength))
        dim = QColor(color)
        dim.setAlpha(int(90 * strength))
        breathe = 0.6
        # right side: 90+GAP .. 270-GAP is the left half (counter-clockwise from top)
        for start, span in ((90 + GAP, 62), (90 + GAP + 66, 14), (90 + GAP + 84, 52)):
            glow_arc(p, rect, start, span, c, 3.0, 0.9 + 0.4 * breathe)
        for start, span in ((270 + GAP, 52), (270 + GAP + 56, 14), (270 + GAP + 74, 62)):
            glow_arc(p, rect, start, span, c, 3.0, 0.9 + 0.4 * breathe)
        # inner thin companion arc with a moving highlight
        rI = R * 0.84
        rect2 = QRectF(cx - rI, cy - rI, rI * 2, rI * 2)
        p.setPen(pen(dim, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect2, int((90 + GAP) * 16), int((180 - 2 * GAP) * 16))
        p.drawArc(rect2, int((270 + GAP) * 16), int((180 - 2 * GAP) * 16))

    def _paint_wave(self, p, cx, cy, R, strength, color) -> None:
        base = R * 0.605
        span = R * 0.18
        halves = [QPolygonF(), QPolygonF()]
        half = len(self._bar_angles) // 2
        buckets: List[List] = [[] for _ in range(6)]
        for i, a in enumerate(self._bar_angles):
            v = min(1.0, self._bars[i])
            length = 2 + span * v
            buckets[min(5, int(v * 1.4 * 6))].append(QLineF(polar(cx, cy, base, a), polar(cx, cy, base + length, a)))
            if self._energy > 0.08:
                halves[i >= half].append(polar(cx, cy, base + length + 3, a))
        for b, lines in enumerate(buckets):
            if not lines:
                continue
            c = QColor(THEME.c("primary_hi") if b >= 3 else color)
            c.setAlpha(int((70 + 185 * (b + 0.5) / 6) * strength))
            p.setPen(pen(c, 2.0))
            p.drawLines(lines)
        # soft envelope glow when there's real energy
        if self._energy > 0.08:
            c = THEME.c("primary_hi", 26 * min(1.0, self._energy * 1.5) * strength)
            p.setPen(pen(c, 4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for poly in halves:
                p.drawPolyline(poly)

    def _coil_layer(self, R) -> QPixmap:
        key = (round(R, 1), THEME.version, round(self.devicePixelRatioF(), 2))
        if getattr(self, "_coil_key", None) != key:
            dpr = self.devicePixelRatioF()
            side = int(R * 1.1) + 8
            pm = QPixmap(int(side * dpr), int(side * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_coils(q, side / 2, side / 2, R, 1.0, THEME.c("primary"), rot=0.0, e=0.55)
            q.end()
            self._coil_pm, self._coil_key = pm, key
        return self._coil_pm

    def _paint_coil_ticks(self, p, cx, cy, R, strength) -> None:
        ri = R * 0.405
        p.save()
        p.translate(cx, cy)
        p.rotate(self._rot[3])
        p.setPen(pen(THEME.c("primary", 140 * strength), 1))
        r0, r1 = ri * 0.80, ri * 0.86
        p.drawLines([QLineF(r0 * math.cos(math.radians(i)), r0 * math.sin(math.radians(i)),
                            r1 * math.cos(math.radians(i)), r1 * math.sin(math.radians(i))) for i in range(0, 360, 6)])
        p.restore()

    def _paint_coils(self, p, cx, cy, R, strength, color, rot=0.0, e=0.5) -> None:
        ri, ro = R * 0.405, R * 0.525
        grad = QRadialGradient(QPointF(cx, cy), ro)
        grad.setColorAt(ri / ro, THEME.c("primary_hi", (110 + 120 * e) * strength))
        grad.setColorAt(0.5 + 0.5 * ri / ro, THEME.c("primary", (70 + 80 * e) * strength))
        grad.setColorAt(1.0, THEME.c("primary_lo", (50 + 60 * e) * strength))
        edge = THEME.c("primary_hi", (150 + 80 * e) * strength)
        hatch = THEME.c("glow", 120 * strength)
        hatch_lines = []
        for k in range(10):
            ca = rot + k * 36
            poly = QPolygonF([polar(cx, cy, ri, ca - 13.5), polar(cx, cy, ro, ca - 12.0),
                              polar(cx, cy, ro, ca + 12.0), polar(cx, cy, ri, ca + 13.5)])
            p.setBrush(QBrush(grad))
            p.setPen(pen(edge, 1))
            p.drawPolygon(poly)
            for j in range(1, 5):          # coil windings
                r = ri + (ro - ri) * j / 5
                hatch_lines.append(QLineF(polar(cx, cy, r, ca - 11.5), polar(cx, cy, r, ca + 11.5)))
        p.setPen(pen(hatch, 1))
        p.drawLines(hatch_lines)
        # retaining ring
        rect = QRectF(cx - ri * 0.93, cy - ri * 0.93, ri * 1.86, ri * 1.86)
        glow_arc(p, rect, 0, 360, THEME.c("primary", 200 * strength), 1.6, 0.8)

    def _paint_core(self, p, cx, cy, R, strength, color) -> None:
        e = self._energy
        breathe = 0.5 + 0.5 * math.sin(self.t * 1.6)
        rc = R * (0.27 + 0.015 * breathe + 0.03 * e)
        g = QRadialGradient(QPointF(cx, cy), rc * 1.6)
        g.setColorAt(0.0, QColor(255, 255, 255, int(235 * strength)))
        g.setColorAt(0.18, THEME.c("primary_hi", 230 * strength))
        g.setColorAt(0.45, THEME.c("primary", (120 + 80 * e) * strength))
        g.setColorAt(0.75, THEME.c("glow", 40 * strength))
        g.setColorAt(1.0, THEME.c("glow", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), rc * 1.6, rc * 1.6)
        # Mk VI triangle
        tri = QPainterPath()
        rt = rc * 0.72
        for i, a in enumerate((90, 210, 330)):
            pt = polar(cx, cy, rt, a + 180)
            tri.moveTo(pt) if i == 0 else tri.lineTo(pt)
        tri.closeSubpath()
        glow_path(p, tri, QColor(255, 255, 255, int(150 * strength)), 1.4, 0.9)
        # rim
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen(THEME.c("primary_hi", 200 * strength), 1.4))
        p.drawEllipse(QPointF(cx, cy), rc, rc)

    def _paint_callouts(self, p, cx, cy, R, k) -> None:
        w = self.width()
        lf = font("ui", 11, 700, 1.8)
        vf = font("mono", 11.5, 500)
        lfm, vfm = QFontMetricsF(lf), QFontMetricsF(vf)
        spots = [(135, -1), (45, 1), (225, -1), (315, 1)]
        for (label, value), (a, side) in zip(self.callouts, spots):
            if not label:
                continue
            p0 = polar(cx, cy, R * 0.995, a)
            p1 = polar(cx, cy, R * 1.10, a)
            room = (cx - R * 1.10 - 8) if side < 0 else (w - (cx + R * 1.10) - 8)
            if room < 90:
                continue
            length = min(room - 4, max(lfm.horizontalAdvance(label), vfm.horizontalAdvance(value)) + 18)
            x_end = p1.x() + side * length * k
            path = QPainterPath(p0)
            path.lineTo(p1)
            path.lineTo(QPointF(x_end, p1.y()))
            glow_path(p, path, THEME.c("primary", 170 * k), 1.0, 0.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c("primary_hi", 230 * k))
            p.drawEllipse(p0, 2.4, 2.4)
            p.drawRect(QRectF(x_end - 1.5, p1.y() - 1.5, 3, 3))
            align = Qt.AlignmentFlag.AlignRight if side < 0 else Qt.AlignmentFlag.AlignLeft
            tx = x_end if side > 0 else x_end - length
            tx = p1.x() + 10 if side > 0 else p1.x() - 10 - (length - 10)
            box = QRectF(tx, p1.y() - 20, length - 10, 17)
            p.setOpacity(k)
            p.setFont(lf)
            p.setPen(THEME.c("text_lo", 255))
            p.drawText(box, int(align | Qt.AlignmentFlag.AlignBottom), label)
            box2 = QRectF(tx, p1.y() + 3, length - 10, 18)
            p.setFont(vf)
            p.setPen(THEME.c("text_hi", 240))
            p.drawText(box2, int(align | Qt.AlignmentFlag.AlignTop), value)
            p.setOpacity(1.0)
