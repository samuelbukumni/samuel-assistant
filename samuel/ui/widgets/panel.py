"""Base panel: chamfered glass frame + header, with a reveal animation."""
from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from samuel.ui.anim import ease_out_cubic
from samuel.ui.paint import header, panel_frame
from samuel.ui.theme import THEME


class Panel(QWidget):
    def __init__(self, index: str, title: str, right: str = "", parent=None):
        super().__init__(parent)
        self.index, self.title, self.right = index, title, right
        self.led = None
        self.reveal = 1.0
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 38, 16, 14)
        self.body.setSpacing(8)
        THEME.changed.connect(self.update)

    def set_right(self, s: str) -> None:
        if s != self.right:
            self.right = s
            self.update()

    def set_led(self, on) -> None:
        if on != self.led:
            self.led = on
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = ease_out_cubic(self.reveal)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if k < 1:
            r = QRectF(r.x(), r.y(), r.width() * (0.6 + 0.4 * k), r.height())
            p.setOpacity(k)
        panel_frame(p, r)
        header(p, r, self.index, self.title, self.right, self.led)
        p.end()
