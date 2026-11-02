"""Palette and typography for the HUD.

`THEME` is a single shared object. Switching persona cross-fades every
colour over ~0.8 s; widgets just call THEME.c("primary", alpha) when they
paint, so they follow the fade automatically.

Fonts are bundled (SIL Open Font License, see samuel/ui/fonts/OFL-*.txt):
  display  Orbitron        wordmark and clock only
  ui       Rajdhani        labels, body text
  mono     JetBrains Mono  numbers, console, telemetry
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase

from samuel.personas import get_persona

FONT_DIR = Path(__file__).parent / "fonts"
_FAMILIES = {"display": "Sans Serif", "ui": "Sans Serif", "mono": "Monospace"}
_WANTED = {"display": "Orbitron", "ui": "Rajdhani", "mono": "JetBrains Mono"}


def load_fonts() -> Dict[str, str]:
    loaded = set()
    for path in sorted(FONT_DIR.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid >= 0:
            loaded.update(QFontDatabase.applicationFontFamilies(fid))
    for role, family in _WANTED.items():
        if family in loaded or family in QFontDatabase.families():
            _FAMILIES[role] = family
    return dict(_FAMILIES)


def font(role: str, px: float, weight: int = 500, spacing: float = 0.0) -> QFont:
    f = QFont(_FAMILIES.get(role, "Sans Serif"))
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(QFont.Weight(weight))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    f.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    return f


class Theme(QObject):
    changed = pyqtSignal()

    def __init__(self, persona: str = "jarvis"):
        super().__init__()
        self.key = get_persona(persona).key
        self._from: Dict[str, Tuple[float, float, float]] = {}
        self._to = {k: tuple(map(float, v)) for k, v in get_persona(self.key).palette.items()}
        self._cur = dict(self._to)
        self._t = 1.0
        self.version = 0          # bumps whenever colours change (for pixmap caches)

    @property
    def animating(self) -> bool:
        return self._t < 1.0

    def set_persona(self, key: str, animate: bool = True) -> None:
        key = get_persona(key).key
        self.key = key
        self._from = dict(self._cur)
        self._to = {k: tuple(map(float, v)) for k, v in get_persona(key).palette.items()}
        self._t = 0.0 if animate else 1.0
        if not animate:
            self._cur = dict(self._to)
        self.version += 1
        self.changed.emit()

    def tick(self, dt: float) -> bool:
        if self._t >= 1.0:
            return False
        self._t = min(1.0, self._t + dt / 0.8)
        e = 1 - (1 - self._t) ** 3
        self._cur = {k: tuple(a + (b - a) * e for a, b in zip(self._from.get(k, v), v))
                     for k, v in self._to.items()}
        self.version += 1
        self.changed.emit()
        return True

    def rgb(self, name: str) -> Tuple[float, float, float]:
        return self._cur.get(name, (255.0, 0.0, 255.0))

    def c(self, name: str, alpha: float = 255) -> QColor:
        r, g, b = self.rgb(name)
        return QColor(int(r), int(g), int(b), max(0, min(255, int(alpha))))

    def mix(self, a: str, b: str, t: float, alpha: float = 255) -> QColor:
        ra, ga, ba = self.rgb(a)
        rb, gb, bb = self.rgb(b)
        t = max(0.0, min(1.0, t))
        return QColor(int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t),
                      max(0, min(255, int(alpha))))

    def level(self, value: float, warn: float, crit: float, alpha: float = 255) -> QColor:
        """Primary below warn, accent up to crit, alert above."""
        if value is None:
            return self.c("text_lo", alpha)
        if value >= crit:
            return self.c("alert", alpha)
        if value >= warn:
            return self.c("accent", alpha)
        return self.c("primary", alpha)


THEME = Theme()
