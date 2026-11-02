"""QPainter helpers shared by the widgets: chamfered frames, fake glow,
polar maths and tracked text."""
from __future__ import annotations

import math
from typing import Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen

from samuel.ui.theme import THEME, font


def polar(cx: float, cy: float, r: float, deg: float) -> QPointF:
    """Point at `deg` degrees (0 = 3 o'clock, counter-clockwise), screen y down."""
    a = math.radians(deg)
    return QPointF(cx + r * math.cos(a), cy - r * math.sin(a))


def chamfer_path(rect: QRectF, cut: float = 10.0, corners: str = "tl br") -> QPainterPath:
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    c = {k: (cut if k in corners.split() else 0.0) for k in ("tl", "tr", "br", "bl")}
    path = QPainterPath()
    path.moveTo(x + c["tl"], y)
    path.lineTo(x + w - c["tr"], y)
    path.lineTo(x + w, y + c["tr"])
    path.lineTo(x + w, y + h - c["br"])
    path.lineTo(x + w - c["br"], y + h)
    path.lineTo(x + c["bl"], y + h)
    path.lineTo(x, y + h - c["bl"])
    path.lineTo(x, y + c["tl"])
    path.closeSubpath()
    return path


def pen(color: QColor, width: float = 1.0, cap=Qt.PenCapStyle.FlatCap) -> QPen:
    p = QPen(color, width)
    p.setCapStyle(cap)
    p.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return p


GLOW = {"passes": 2}        # set to 0 by --lite


def glow_path(p: QPainter, path: QPainterPath, color: QColor, width: float = 1.5,
              strength: float = 1.0, cap=Qt.PenCapStyle.FlatCap) -> None:
    """Fake bloom: two wide, faint strokes under the real one."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    for extra, alpha in ((width * 4 + 4, 0.07), (width * 2 + 1.5, 0.16))[2 - GLOW["passes"]:]:
        c = QColor(color)
        c.setAlphaF(max(0.0, min(1.0, color.alphaF() * alpha * strength)))
        p.setPen(pen(c, extra, cap))
        p.drawPath(path)
    p.setPen(pen(color, width, cap))
    p.drawPath(path)


def glow_arc(p: QPainter, rect: QRectF, start_deg: float, span_deg: float, color: QColor,
             width: float = 2.0, strength: float = 1.0, cap=Qt.PenCapStyle.FlatCap) -> None:
    path = QPainterPath()
    path.arcMoveTo(rect, start_deg)
    path.arcTo(rect, start_deg, span_deg)
    glow_path(p, path, color, width, strength, cap)


def text(p: QPainter, rect: QRectF, s: str, role: str, px: float, color: QColor,
         align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
         weight: int = 500, spacing: float = 0.0) -> None:
    p.setFont(font(role, px, weight, spacing))
    p.setPen(color)
    p.drawText(rect, int(align), s)


def panel_frame(p: QPainter, rect: QRectF, cut: float = 12.0, emphasis: float = 1.0,
                fill_alpha: float = 1.0) -> None:
    """The signature HUD frame: chamfered glassy panel with bright corners."""
    path = chamfer_path(rect, cut, "tl br")
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    grad.setColorAt(0.0, THEME.c("bg1", 170 * fill_alpha))
    grad.setColorAt(1.0, THEME.c("bg0", 150 * fill_alpha))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawPath(path)
    tint = QLinearGradient(rect.topLeft(), rect.bottomRight())
    tint.setColorAt(0.0, THEME.c("primary", 16 * fill_alpha))
    tint.setColorAt(0.6, THEME.c("primary", 4 * fill_alpha))
    tint.setColorAt(1.0, THEME.c("primary", 10 * fill_alpha))
    p.setBrush(QBrush(tint))
    p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen(THEME.c("primary", 52 * emphasis), 1.0))
    p.drawPath(path)

    # bright corner accents
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    accent = THEME.c("primary", 210 * emphasis)
    corner = QPainterPath()
    corner.moveTo(x, y + cut + 16)
    corner.lineTo(x, y + cut)
    corner.lineTo(x + cut, y)
    corner.lineTo(x + cut + 22, y)
    corner.moveTo(x + w, y + h - cut - 16)
    corner.lineTo(x + w, y + h - cut)
    corner.lineTo(x + w - cut, y + h)
    corner.lineTo(x + w - cut - 22, y + h)
    glow_path(p, corner, accent, 1.6, 0.8)
    # small square studs on the plain corners
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(THEME.c("primary", 140 * emphasis))
    p.drawRect(QRectF(x + w - 4, y, 4, 4))
    p.drawRect(QRectF(x, y + h - 4, 4, 4))


def header(p: QPainter, rect: QRectF, index: str, title: str, right: str = "",
           led: Optional[bool] = None) -> float:
    """Panel header row; returns the y below it."""
    x, y, w = rect.x() + 16, rect.y() + 9, rect.width() - 32
    p.setFont(font("mono", 10, 500))
    p.setPen(THEME.c("primary", 190))
    p.drawText(QRectF(x, y, 30, 16), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), index)
    tf = font("ui", 13.5, 700, 2.6)
    p.setFont(tf)
    p.setPen(THEME.c("text_hi", 235))
    tx = x + 26
    p.drawText(QRectF(tx, y - 1, w, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), title)
    from PyQt6.QtGui import QFontMetricsF
    tw = QFontMetricsF(tf).horizontalAdvance(title)
    rx = x + w
    if led is not None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("ok" if led else "text_lo", 230 if led else 120))
        p.drawEllipse(QPointF(rx - 3, y + 8), 2.6, 2.6)
        if led:
            p.setBrush(THEME.c("ok", 50))
            p.drawEllipse(QPointF(rx - 3, y + 8), 6, 6)
        rx -= 14
    rw = 0.0
    rf = font("mono", 9.5, 500, 0.6)
    if right and rx - QFontMetricsF(rf).horizontalAdvance(right) < tx + tw + 30:
        right = ""                      # not enough room: drop the right label
    if right:
        p.setFont(rf)
        p.setPen(THEME.c("text_lo", 230))
        rw = QFontMetricsF(rf).horizontalAdvance(right)
        p.drawText(QRectF(rx - rw, y, rw + 1, 16), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right)
    # rule with ticks between title and right label
    lx0, lx1 = tx + tw + 10, rx - rw - (10 if right else 0)
    ly = y + 8.5
    if lx1 - lx0 > 20:
        p.setPen(pen(THEME.c("primary", 45), 1))
        p.drawLine(QPointF(lx0, ly), QPointF(lx1, ly))
        p.setPen(pen(THEME.c("primary", 120), 1))
        for i in range(3):
            xx = lx1 - 2 - i * 5
            p.drawLine(QPointF(xx, ly - 2.5), QPointF(xx, ly + 2.5))
    return rect.y() + 34


def wrap(fm, s: str, width: float, max_lines: int = 0) -> list:
    """Greedy word wrap with QFontMetricsF; ellipsises the last line."""
    words = (s or "").split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if fm.horizontalAdvance(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and fm.horizontalAdvance(last + "…") > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines
