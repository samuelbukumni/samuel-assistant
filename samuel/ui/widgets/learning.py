"""Right column: the learning matrix (progress, active lesson, quiz/flashcards)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from samuel.ui.anim import approach, ease_out_cubic
from samuel.ui.paint import chamfer_path, glow_path, pen, wrap
from samuel.ui.theme import THEME, font
from samuel.ui.widgets.panel import Panel

AL = Qt.AlignmentFlag
GRADES = [("AGAIN", 1), ("HARD", 3), ("GOOD", 4), ("EASY", 5)]


def label(p, rect, s, color="text_mid", px=11.5, alpha=235, align=AL.AlignLeft):
    p.setFont(font("ui", px, 700, 1.8))
    p.setPen(THEME.c(color, alpha))
    p.drawText(rect, int(align | AL.AlignVCenter), s)


class StatsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.s: Dict = {}
        self.setFixedHeight(122)

    def set_stats(self, s: Dict):
        self.s = s or {}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        s = self.s
        blocks = [("STREAK", s.get("streak", 0), "DAYS", "accent"), ("DUE", s.get("due", 0), "CARDS", "primary_hi"),
                  ("MASTERED", s.get("mastered", 0), f"OF {s.get('cards', 0)}", "ok")]
        bw = (w - 16) / 3
        for i, (k, v, unit, col) in enumerate(blocks):
            x = i * (bw + 8)
            r = QRectF(x, 0, bw, 58)
            p.setPen(pen(THEME.c("primary", 45), 1))
            p.setBrush(THEME.c("primary", 10))
            p.drawPath(chamfer_path(r, 6, "tr"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c(col, 230))
            p.drawRect(QRectF(x, 0, 2, 58))
            label(p, QRectF(x + 10, 4, bw - 14, 14), k, "text_lo", 10.5)
            p.setFont(font("mono", 24, 500))
            p.setPen(THEME.c("text_hi", 250))
            num = f"{v:02d}" if isinstance(v, int) else str(v)
            p.drawText(QRectF(x + 10, 18, bw - 14, 30), int(AL.AlignLeft | AL.AlignVCenter), num)
            p.setFont(font("mono", 8.5, 500))
            p.setPen(THEME.c(col, 220))
            p.drawText(QRectF(x + 10, 44, bw - 14, 12), int(AL.AlignLeft | AL.AlignVCenter), unit)
        # last 7 days
        y = 70
        label(p, QRectF(0, y, 80, 16), "7-DAY", "text_lo", 10.5)
        days = s.get("last7") or [False] * 7
        today = date.today()
        dx0, span = 52, w - 52
        for i, active in enumerate(days):
            d = today - timedelta(days=6 - i)
            cx = dx0 + span * (i + 0.5) / 7
            r = 5.0
            if active:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(THEME.c("accent", 50))
                p.drawEllipse(QPointF(cx, y + 6), r + 4, r + 4)
                p.setBrush(THEME.c("accent", 240))
                p.drawEllipse(QPointF(cx, y + 6), r, r)
            else:
                p.setPen(pen(THEME.c("primary", 90 if i < 6 else 160), 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, y + 6), r, r)
            p.setFont(font("mono", 8, 500))
            p.setPen(THEME.c("text_hi" if i == 6 else "text_lo", 230))
            p.drawText(QRectF(cx - 12, y + 13, 24, 12), int(AL.AlignHCenter | AL.AlignVCenter), "MTWTFSS"[d.weekday()])
        y = 100
        rv, ok = s.get("reviews_today", 0), s.get("correct_today", 0)
        acc = f"{round(100 * ok / rv)}%" if rv else "--"
        items = [("TODAY", f"{rv} REVIEW{'S' if rv != 1 else ''}"), ("RECALL", acc), ("LESSONS", str(s.get("lessons", 0)))]
        cw = w / 3
        for i, (k, v) in enumerate(items):
            p.setFont(font("ui", 10.5, 700, 1.4))
            p.setPen(THEME.c("text_lo", 255))
            kw = QFontMetricsF(p.font()).horizontalAdvance(k + "  ")
            x = i * cw
            p.drawText(QRectF(x, y, kw, 18), int(AL.AlignLeft | AL.AlignVCenter), k)
            p.setFont(font("mono", 10, 500))
            p.setPen(THEME.c("text_hi", 235))
            p.drawText(QRectF(x + kw, y, cw - kw, 18), int(AL.AlignLeft | AL.AlignVCenter), v)
        p.end()


class LessonView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lesson: Dict = {}
        self.fade = 1.0
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_lesson(self, d: Dict):
        changed = (d or {}).get("point") != self.lesson.get("point")
        self.lesson = d or {}
        if changed:
            self.fade = 0.0
        self.update()

    def advance(self, dt):
        if self.fade < 1:
            self.fade = min(1.0, self.fade + dt / 0.35)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(pen(THEME.c("primary", 40), 1))
        p.drawLine(0, 0, w, 0)
        L = self.lesson
        label(p, QRectF(0, 8, w, 14), "ACTIVE LESSON")
        if not L:
            p.setFont(font("ui", 19, 600))
            p.setPen(THEME.c("text_mid", 200))
            p.drawText(QRectF(0, 28, w, 26), int(AL.AlignLeft | AL.AlignVCenter), "No lesson loaded")
            p.setFont(font("ui", 13.5, 500))
            p.setPen(THEME.c("text_lo", 255))
            fm = QFontMetricsF(p.font())
            for i, line in enumerate(wrap(fm, "Say or type “teach me about black holes”. Lessons are built from "
                                             "Wikipedia and cached for offline study.", w, 4)):
                p.drawText(QRectF(0, 58 + i * 19, w, 19), int(AL.AlignLeft | AL.AlignVCenter), line)
            p.end()
            return
        idx, total = L.get("index", 0), max(1, L.get("total", 1))
        p.setFont(font("mono", 9.5, 500))
        p.setPen(THEME.c("primary_hi", 230))
        p.drawText(QRectF(0, 8, w, 14), int(AL.AlignRight | AL.AlignVCenter), f"POINT {idx + 1:02d}/{total:02d}")
        tf = font("ui", 22, 700, 0.4)
        p.setFont(tf)
        p.setPen(THEME.c("text_hi", 250))
        title = wrap(QFontMetricsF(tf), L.get("title", ""), w, 1)
        p.drawText(QRectF(0, 25, w, 28), int(AL.AlignLeft | AL.AlignVCenter), title[0] if title else "")
        y = 54
        if L.get("description"):
            p.setFont(font("ui", 12.5, 500, 0.4))
            p.setPen(THEME.c("text_lo", 255))
            d = wrap(QFontMetricsF(p.font()), L["description"], w, 1)
            p.drawText(QRectF(0, y, w, 16), int(AL.AlignLeft | AL.AlignVCenter), d[0] if d else "")
            y += 20
        # progress segments
        gap = 3
        sw = (w - gap * (total - 1)) / total
        for i in range(total):
            r = QRectF(i * (sw + gap), y + 2, sw, 4)
            p.fillRect(r, THEME.c("primary_hi" if i == idx else "primary", 255 if i == idx else (150 if i < idx else 30)))
        y += 16
        # point text
        p.setOpacity(ease_out_cubic(self.fade))
        pf = font("ui", 15, 500, 0.2)
        p.setFont(pf)
        p.setPen(THEME.c("text_hi", 235))
        fm = QFontMetricsF(pf)
        lh = fm.height() * 1.12
        lines = wrap(fm, L.get("point", ""), w - 12, max(1, int((h - y) // lh)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("primary", 150))
        p.drawRect(QRectF(0, y + 3, 2, lh * len(lines) - 6))
        p.setPen(THEME.c("text_hi", 235))
        for i, line in enumerate(lines):
            p.drawText(QRectF(12, y + i * lh, w - 12, lh), int(AL.AlignLeft | AL.AlignVCenter), line)
        p.end()


class CardView(QWidget):
    answer = pyqtSignal(int)
    grade = pyqtSignal(int)
    reveal = pyqtSignal()
    suggest = pyqtSignal(str)

    SUGGESTIONS = ["teach me about black holes", "quiz me", "review my flashcards", "how am I doing"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.card: Dict = {}
        self.fade = 1.0
        self.hover = -1
        self._hits: List[Tuple[QRectF, str, int]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_card(self, c: Dict):
        key = lambda d: (d.get("type"), d.get("index"), d.get("title"))   # noqa: E731
        if key(c or {}) != key(self.card):
            self.fade = 0.0
        self.card = c or {}
        self.update()

    def advance(self, dt):
        if self.fade < 1:
            self.fade = min(1.0, self.fade + dt / 0.3)
            self.update()

    # interaction -----------------------------------------------------------
    def mouseMoveEvent(self, e):
        idx = -1
        for i, (r, _, _) in enumerate(self._hits):
            if r.contains(e.position()):
                idx = i
        if idx != self.hover:
            self.hover = idx
            self.setCursor(Qt.CursorShape.PointingHandCursor if idx >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        for r, kind, val in self._hits:
            if r.contains(e.position()):
                if kind == "answer":
                    self.answer.emit(val)
                elif kind == "grade":
                    self.grade.emit(val)
                elif kind == "reveal":
                    self.reveal.emit()
                elif kind == "suggest":
                    self.suggest.emit(self.SUGGESTIONS[val])
                return

    # painting ----------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hits = []
        w, h = self.width(), self.height()
        p.setPen(pen(THEME.c("primary", 40), 1))
        p.drawLine(0, 0, w, 0)
        k = ease_out_cubic(self.fade)
        p.setOpacity(k)
        p.translate(0, (1 - k) * 10)
        t = self.card.get("type")
        if t == "quiz":
            self._quiz(p, w, h)
        elif t == "flash":
            self._flash(p, w, h)
        elif t == "result":
            self._result(p, w, h)
        else:
            self._empty(p, w, h)
        p.end()

    def _button(self, p, r: QRectF, text: str, idx_hit: int, state: str = "", key: str = "", big=False):
        hov = idx_hit == self.hover
        col = {"ok": "ok", "bad": "alert", "dim": "text_lo"}.get(state, "primary")
        path = chamfer_path(r, 7, "tl br")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c(col, 60 if state in ("ok", "bad") else (38 if hov else 14)))
        p.drawPath(path)
        glow_path(p, path, THEME.c(col, 230 if (hov or state in ("ok", "bad")) else 90), 1.0, 0.5 if hov else 0.2)
        x = r.x() + (10 if not big else 7)
        if key:
            kr = QRectF(x, r.center().y() - 10, 20, 20)
            p.setPen(pen(THEME.c(col, 200), 1))
            p.setBrush(THEME.c(col, 40))
            p.drawRect(kr)
            p.setFont(font("mono", 10.5, 600))
            p.setPen(THEME.c("text_hi", 250))
            p.drawText(kr, int(AL.AlignCenter), key)
            x += 30 if not big else 26
        f = font("ui", 14 if not big else 12.5, 600 if not big else 700, 0.3 if not big else 1.0)
        p.setFont(f)
        p.setPen(THEME.c("text_hi", 245 if state != "dim" else 140))
        lines = wrap(QFontMetricsF(f), text, r.right() - x - 8, 2)
        lh = QFontMetricsF(f).height()
        y0 = r.center().y() - lh * len(lines) / 2
        for i, line in enumerate(lines):
            p.drawText(QRectF(x, y0 + i * lh, r.right() - x - 6, lh), int(AL.AlignLeft | AL.AlignVCenter), line)

    def _head(self, p, w, left, right):
        label(p, QRectF(0, 8, w, 14), left)
        p.setFont(font("mono", 9.5, 500))
        p.setPen(THEME.c("primary_hi", 230))
        p.drawText(QRectF(0, 8, w, 14), int(AL.AlignRight | AL.AlignVCenter), right)

    def _quiz(self, p, w, h):
        c = self.card
        self._head(p, w, f"QUIZ · {c.get('title', '').upper()}"[:34],
                   f"Q{c.get('index', 0) + 1}/{c.get('total', 0)}  ·  SCORE {c.get('score', 0)}")
        pf = font("ui", 16, 600, 0.2)
        fm = QFontMetricsF(pf)
        lines = wrap(fm, c.get("prompt", "").replace("_____", "______"), w, 5)
        lh = fm.height() * 1.1
        p.setFont(pf)
        p.setPen(THEME.c("text_hi", 245))
        y = 30
        for i, line in enumerate(lines):
            p.drawText(QRectF(0, y + i * lh, w, lh), int(AL.AlignLeft | AL.AlignVCenter), line)
        y += lh * len(lines) + 12
        opts = c.get("options", [])
        sel, ans = c.get("selected"), c.get("answer")
        bh = min(44.0, max(34.0, (h - y - 26) / max(1, len(opts)) - 7))
        for i, o in enumerate(opts):
            r = QRectF(0, y, w, bh)
            state = ""
            if ans is not None:
                state = "ok" if i == ans else "bad" if i == sel else "dim"
            self._hits.append((r, "answer", i))
            self._button(p, r, o, len(self._hits) - 1, state, "ABCD"[i])
            y += bh + 7
        p.setFont(font("mono", 9, 500))
        p.setPen(THEME.c("text_lo", 255))
        hint = "PRESS 1–4 OR SAY “B”" if ans is None else "SPACE / “NEXT” TO CONTINUE"
        p.drawText(QRectF(0, y + 2, w, 14), int(AL.AlignLeft | AL.AlignVCenter), hint)

    def _flash(self, p, w, h):
        c = self.card
        self._head(p, w, f"FLASHCARD · {c.get('title', '').upper()}"[:36], f"{c.get('index', 0) + 1}/{c.get('total', 0)} DUE")
        r = QRectF(0, 30, w, h - 30 - 52)
        path = chamfer_path(r, 14, "tl br")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("primary", 12))
        p.drawPath(path)
        glow_path(p, path, THEME.c("primary", 120), 1.0, 0.4)
        revealed = bool(c.get("revealed"))
        pf = font("ui", 19 if not revealed else 16, 600, 0.2)
        fm = QFontMetricsF(pf)
        p.setFont(pf)
        p.setPen(THEME.c("text_hi", 245))
        lh = fm.height() * 1.12
        lines = wrap(fm, c.get("front", ""), w - 36, 6)
        block = lh * len(lines)
        y = r.y() + 16 if revealed else r.y() + max(16.0, (r.height() - block) / 2 - 8)
        label(p, QRectF(18, r.y() + 10, w - 36, 14), "FRONT" if not revealed else "", "text_lo", 10)
        for i, line in enumerate(lines):
            p.drawText(QRectF(18, y + i * lh, w - 36, lh),
                       int((AL.AlignHCenter if not revealed else AL.AlignLeft) | AL.AlignVCenter), line)
        y += block + 12
        if c.get("revealed"):
            p.setPen(pen(THEME.c("primary", 70), 1))
            p.drawLine(QPointF(18, y), QPointF(w - 18, y))
            verdict = c.get("verdict")
            if verdict is not None:
                label(p, QRectF(18, y + 6, w - 36, 14), "CORRECT" if verdict else "NOT QUITE",
                      "ok" if verdict else "alert", 11)
                y += 18
            af = font("ui", 19, 700, 0.3)
            p.setFont(af)
            p.setPen(THEME.c("primary_hi", 255))
            for i, line in enumerate(wrap(QFontMetricsF(af), c.get("back", ""), w - 36, 3)):
                p.drawText(QRectF(18, y + 8 + i * 26, w - 36, 26), int(AL.AlignLeft | AL.AlignVCenter), line)
            gw = (w - 3 * 6) / 4
            for i, (name, q) in enumerate(GRADES):
                br = QRectF(i * (gw + 6), h - 44, gw, 38)
                self._hits.append((br, "grade", q))
                self._button(p, br, name, len(self._hits) - 1, "", str(i + 1), big=True)
        else:
            br = QRectF(0, h - 44, w, 38)
            self._hits.append((br, "reveal", 0))
            self._button(p, br, "SHOW ANSWER", len(self._hits) - 1, "", "␣", big=True)

    def _result(self, p, w, h):
        c = self.card
        quiz = c.get("score") is not None
        self._head(p, w, ("QUIZ COMPLETE · " if quiz else "REVIEW COMPLETE · ") + c.get("title", "").upper()[:20], "")
        total = c.get("total", 0)
        big = f"{c.get('score', 0)}/{total}" if quiz else f"{total}"
        p.setFont(font("display", 46, 700, 2))
        p.setPen(THEME.c("text_hi", 250))
        p.drawText(QRectF(0, 34, w, 70), int(AL.AlignLeft | AL.AlignVCenter), big)
        label(p, QRectF(0, 104, w, 16), "CORRECT ANSWERS" if quiz else "CARDS REVIEWED", "primary_hi", 12)
        pct = (c.get("score", 0) / total) if (quiz and total) else 1.0
        bar = QRectF(0, 130, w, 6)
        p.fillRect(bar, THEME.c("primary", 30))
        p.fillRect(QRectF(0, 130, w * pct, 6), THEME.c("ok" if pct >= 0.8 else "accent" if pct >= 0.5 else "alert"))
        self._suggest_rows(p, w, 156, ["review my flashcards", "next", "quiz me"])

    def _empty(self, p, w, h):
        self._head(p, w, "TRAINING QUEUE", "READY")
        p.setFont(font("ui", 14, 500, 0.2))
        p.setPen(THEME.c("text_mid", 235))
        fm = QFontMetricsF(p.font())
        lines = wrap(fm, "Quizzes and due flashcards appear here. Click a suggestion or speak it.", w, 3)
        for i, line in enumerate(lines):
            p.drawText(QRectF(0, 30 + i * 19, w, 19), int(AL.AlignLeft | AL.AlignVCenter), line)
        self._suggest_rows(p, w, 36 + 19 * len(lines), self.SUGGESTIONS)

    def _suggest_rows(self, p, w, y, items):
        for i, s in enumerate(items):
            if s not in self.SUGGESTIONS:
                self.SUGGESTIONS.append(s)
            r = QRectF(0, y, w, 34)
            self._hits.append((r, "suggest", self.SUGGESTIONS.index(s)))
            hov = len(self._hits) - 1 == self.hover
            p.setPen(pen(THEME.c("primary", 120 if hov else 45), 1))
            p.setBrush(THEME.c("primary", 30 if hov else 8))
            p.drawPath(chamfer_path(r, 6, "br"))
            p.setFont(font("mono", 11, 500))
            p.setPen(THEME.c("primary_hi", 240))
            p.drawText(QRectF(12, y, 20, 34), int(AL.AlignLeft | AL.AlignVCenter), "›")
            p.setFont(font("ui", 14, 600, 0.3))
            p.setPen(THEME.c("text_hi", 240 if hov else 215))
            p.drawText(QRectF(30, y, w - 40, 34), int(AL.AlignLeft | AL.AlignVCenter), f"“{s}”")
            y += 40


class LearningPanel(Panel):
    def __init__(self, parent=None):
        super().__init__("03", "LEARNING MATRIX", "SM-2 · OFFLINE CACHE", parent)
        self.stats = StatsView()
        self.lesson = LessonView()
        self.card = CardView()
        self.body.setSpacing(10)
        self.body.addWidget(self.stats)
        self.body.addWidget(self.lesson, 3)
        self.body.addWidget(self.card, 5)

    def advance(self, dt):
        self.lesson.advance(dt)
        self.card.advance(dt)
