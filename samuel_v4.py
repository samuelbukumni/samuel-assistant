"""
S.A.M.U.E.L v4 — Personal AI Assistant
Cross-platform | Offline-first STT | JARVIS Arc Reactor UI
Author: Samuel (OAU)

DEPENDENCIES:
    pip install pyqt6 vosk pyaudio psutil wikipedia requests speechrecognition pyautogui

PLATFORM NOTES:
    Linux  : aplay for audio output (already working)
    Windows: pip install pywin32 — uses winsound/powershell for TTS fallback
    Android: Use Termux + termux-microphone-record (future phase)

VOSK MODEL:
    Place model folder at ~/samuel_voice/vosk-model-small-en-in-0.4/
    Download: https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip
"""

import sys
import os
import platform
import datetime
import threading
import time
import json
import subprocess
import queue
import math

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                              QHBoxLayout, QLineEdit, QTextEdit, QFrame,
                              QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QPointF, QRectF
from PyQt6.QtGui import (QFont, QPainter, QColor, QPen, QBrush,
                          QRadialGradient, QConicalGradient, QPainterPath,
                          QFontDatabase)

# ─────────────────────────────────────────────
#  PLATFORM DETECTION
# ─────────────────────────────────────────────
PLATFORM = platform.system()   # 'Linux', 'Windows', 'Darwin'
IS_LINUX   = PLATFORM == 'Linux'
IS_WINDOWS = PLATFORM == 'Windows'

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
HOME             = os.path.expanduser("~")
VOSK_MODEL_PATH  = os.path.join(HOME, "samuel_voice", "vosk-model-small-en-in-0.4")
PIPER_EXE        = os.path.join(HOME, "samuel_voice", "piper", "piper")
PIPER_MODEL      = os.path.join(HOME, "samuel_voice", "piper", "en_GB-alan-medium.onnx")
NOTES_DIR        = os.path.join(HOME, "Documents", "SAMUEL_Notes")
NOTES_FILE       = os.path.join(NOTES_DIR, "study_notes.md")
LOG_FILE         = os.path.join(NOTES_DIR, "command_log.txt")
SCREEN_DIR       = os.path.join(HOME, "Documents", "SAMUEL_Screenshots")

WAKE_WORD = "samuel"

# ─────────────────────────────────────────────
#  SIGNALS
# ─────────────────────────────────────────────
class Communicate(QObject):
    update_status  = pyqtSignal(str)   # STATUS TEXT
    update_log     = pyqtSignal(str)   # CONSOLE LINE
    speak          = pyqtSignal(str)   # TTS
    set_wave_level = pyqtSignal(float) # 0.0 – 1.0 mic energy

# ─────────────────────────────────────────────
#  ARC REACTOR WIDGET
# ─────────────────────────────────────────────
class ArcReactor(QWidget):
    """Animated JARVIS-style arc reactor with rotating rings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._angle1   = 0.0   # outer ring rotation
        self._angle2   = 0.0   # inner ring (reverse)
        self._angle3   = 0.0   # data ring
        self._energy   = 0.0   # mic energy 0–1
        self._pulse    = 0.0   # core pulse
        self._pulse_dir = 1
        self._status   = "STANDBY"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)   # ~33fps

    def set_energy(self, val: float):
        self._energy = max(0.0, min(1.0, val))

    def set_status(self, text: str):
        self._status = text.upper()

    def _tick(self):
        speed = 1.0 + self._energy * 4.0
        self._angle1 = (self._angle1 + 0.8 * speed) % 360
        self._angle2 = (self._angle2 - 1.2 * speed) % 360
        self._angle3 = (self._angle3 + 2.0 * speed) % 360

        self._pulse += 0.04 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse_dir = 1

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        base_blue  = QColor(0, 180, 255)
        glow_blue  = QColor(0, 210, 255, 80)
        dim_blue   = QColor(0, 120, 200, 120)
        core_color = QColor(180, 240, 255)
        dark_bg    = QColor(5, 10, 20)

        # ── background circle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dark_bg))
        p.drawEllipse(QPointF(cx, cy), 105, 105)

        # ── outer glow ring
        glow_pen = QPen(glow_blue, 18)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(glow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 95, 95)

        # ── RING 1 — segmented outer ring (rotates CW)
        self._draw_segmented_ring(p, cx, cy, 90, 16, 18, self._angle1,
                                  base_blue, dim_blue, 3.0)

        # ── RING 2 — dashed middle ring (rotates CCW)
        self._draw_segmented_ring(p, cx, cy, 68, 10, 28, self._angle2,
                                  QColor(0, 160, 240), QColor(0, 60, 100, 80), 2.5)

        # ── RING 3 — data tick ring (fast)
        self._draw_tick_ring(p, cx, cy, 50, self._angle3)

        # ── CORE GLOW
        energy_alpha = int(100 + self._pulse * 80 + self._energy * 60)
        core_glow = QRadialGradient(cx, cy, 38)
        core_glow.setColorAt(0.0, QColor(100, 220, 255, energy_alpha))
        core_glow.setColorAt(0.5, QColor(0, 160, 220, energy_alpha // 2))
        core_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core_glow))
        p.drawEllipse(QPointF(cx, cy), 38, 38)

        # ── CORE HEXAGON
        self._draw_hex(p, cx, cy, 22, base_blue, core_color)

        # ── CORE DOT
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core_color))
        p.drawEllipse(QPointF(cx, cy), 6, 6)

        # ── STATUS TEXT (inside ring)
        p.setPen(QPen(QColor(0, 200, 255, 200)))
        font = QFont("Courier New", 7, QFont.Weight.Bold)
        p.setFont(font)
        text_rect = QRectF(cx - 40, cy + 28, 80, 16)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._status)

    def _draw_segmented_ring(self, p, cx, cy, r, count, gap_deg,
                              start_angle, color_on, color_off, width):
        seg = (360 - count * gap_deg) / count
        pen_on  = QPen(color_on,  width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.FlatCap)
        pen_off = QPen(color_off, width * 0.4, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.FlatCap)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        for i in range(count):
            angle = start_angle + i * (seg + gap_deg)
            p.setPen(pen_on if i % 2 == 0 else pen_off)
            p.drawArc(rect,
                      int(angle * 16),
                      int(seg * 16))

    def _draw_tick_ring(self, p, cx, cy, r, offset):
        for i in range(24):
            angle_deg = offset + i * 15
            angle_rad = math.radians(angle_deg)
            tick_len = 6 if i % 6 == 0 else 3
            x1 = cx + (r - tick_len) * math.cos(angle_rad)
            y1 = cy - (r - tick_len) * math.sin(angle_rad)
            x2 = cx + r * math.cos(angle_rad)
            y2 = cy - r * math.sin(angle_rad)
            alpha = 200 if i % 6 == 0 else 80
            p.setPen(QPen(QColor(0, 200, 255, alpha), 1.5))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_hex(self, p, cx, cy, r, border_color, fill_color):
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.setPen(QPen(border_color, 1.5))
        p.setBrush(QBrush(QColor(0, 30, 50, 180)))
        p.drawPath(path)


# ─────────────────────────────────────────────
#  CONSOLE WIDGET
# ─────────────────────────────────────────────
class Console(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumHeight(160)
        self.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #00d4ff;
                border: none;
                font-family: 'Courier New', monospace;
                font-size: 10px;
                selection-background-color: #003344;
            }
        """)
        self.document().setMaximumBlockCount(60)

    def push(self, text: str, color="#00d4ff"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.append(f'<span style="color:#005577;">[{ts}]</span> '
                    f'<span style="color:{color};">{text}</span>')
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum())


# ─────────────────────────────────────────────
#  MAIN HUD
# ─────────────────────────────────────────────
class SamuelHUD(QWidget):
    def __init__(self, comm: Communicate):
        super().__init__()
        self.comm = comm
        self._drag_pos = None
        self._build_ui()

        comm.update_status.connect(self._on_status)
        comm.update_log.connect(self._on_log)
        comm.speak.connect(self._on_speak)
        comm.set_wave_level.connect(self.reactor.set_energy)

    # ── UI CONSTRUCTION ──────────────────────
    def _build_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 560)

        # ── outer shell
        shell = QFrame(self)
        shell.setGeometry(0, 0, 480, 560)
        shell.setStyleSheet("""
            QFrame {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.8,
                    fx:0.5, fy:0.5,
                    stop:0 rgba(5, 15, 30, 245),
                    stop:1 rgba(2, 6, 14, 250));
                border: 1px solid rgba(0, 180, 255, 60);
                border-radius: 4px;
            }
        """)

        root = QVBoxLayout(shell)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── header bar
        header_row = QHBoxLayout()
        self._title = QLabel("S·A·M·U·E·L")
        self._title.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        self._title.setStyleSheet("color: rgba(0,200,255,200); letter-spacing: 4px;")

        self._version = QLabel("v4.0 // STARK PROTOCOL")
        self._version.setFont(QFont("Courier New", 7))
        self._version.setStyleSheet("color: rgba(0,140,200,120);")
        self._version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_row.addWidget(self._title)
        header_row.addWidget(self._version)
        root.addLayout(header_row)

        # ── top divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: rgba(0,180,255,40);")
        root.addWidget(divider)

        # ── reactor + side stats
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        self.reactor = ArcReactor()
        mid_row.addWidget(self.reactor)

        # side panel
        side = QVBoxLayout()
        side.setSpacing(6)

        self._status_label = self._make_stat_label("STATUS", "STANDBY")
        self._time_label   = self._make_stat_label("TIME",   "--:-- --")
        self._cpu_label    = self._make_stat_label("CPU",    "--%")
        self._ram_label    = self._make_stat_label("RAM",    "--%")
        self._bat_label    = self._make_stat_label("POWER",  "--%")
        self._mode_label   = self._make_stat_label("MODE",   "OFFLINE")

        side.addWidget(self._status_label)
        side.addWidget(self._time_label)
        side.addWidget(self._cpu_label)
        side.addWidget(self._ram_label)
        side.addWidget(self._bat_label)
        side.addWidget(self._mode_label)
        side.addStretch()
        mid_row.addLayout(side)
        root.addLayout(mid_row)

        # ── divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("color: rgba(0,180,255,40);")
        root.addWidget(div2)

        # ── console
        self.console = Console()
        root.addWidget(self.console)

        # ── input bar
        input_row = QHBoxLayout()
        self._prompt = QLabel("▶")
        self._prompt.setStyleSheet("color: #00d4ff; font-family: 'Courier New'; font-size: 11px;")

        self._input = QLineEdit()
        self._input.setPlaceholderText("manual override...")
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 30, 50, 180);
                color: #00d4ff;
                border: 1px solid rgba(0,160,220,80);
                border-radius: 2px;
                padding: 4px 8px;
                font-family: 'Courier New';
                font-size: 10px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(0,200,255,160);
            }
        """)
        self._input.returnPressed.connect(self._manual_cmd)

        input_row.addWidget(self._prompt)
        input_row.addWidget(self._input)
        root.addLayout(input_row)

        # ── footer
        footer = QLabel("DRAG TO MOVE  ·  RIGHT-CLICK TO TERMINATE")
        footer.setFont(QFont("Courier New", 6))
        footer.setStyleSheet("color: rgba(0,100,140,100);")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

        # ── system stats ticker
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(2000)
        self._update_stats()

    def _make_stat_label(self, key: str, val: str) -> QLabel:
        lbl = QLabel(f"{key}  <span style='color:#00d4ff;'>{val}</span>")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet("color: rgba(0,120,160,180);")
        lbl.setProperty("key", key)
        lbl.setProperty("val_color", "#00d4ff")
        return lbl

    def _set_stat(self, lbl: QLabel, key: str, val: str, color="#00d4ff"):
        lbl.setText(f"<span style='color:rgba(0,120,160,180);'>{key}</span>"
                    f"  <span style='color:{color};'>{val}</span>")

    # ── SLOTS ────────────────────────────────
    def _on_status(self, text: str):
        t = text.upper()
        self.reactor.set_status(t)
        color_map = {
            "LISTENING": "#00ff88",
            "SPEAKING":  "#ffaa00",
            "ANALYZING": "#ff6600",
            "SEARCHING": "#aa44ff",
            "CAPTURING": "#ff4488",
            "OFFLINE":   "#ff2222",
            "LOADING":   "#ffdd00",
            "STANDBY":   "#00d4ff",
        }
        color = color_map.get(t, "#00d4ff")
        self._set_stat(self._status_label, "STATUS", t, color)

    def _on_log(self, text: str):
        self.console.push(text)

    def _on_speak(self, text: str):
        threading.Thread(target=_speak, args=(text,), daemon=True).start()

    def _manual_cmd(self):
        cmd = self._input.text().strip()
        self._input.clear()
        if cmd:
            self.console.push(f"MANUAL: {cmd}", "#ffaa00")
            threading.Thread(target=core_logic,
                             args=(self.comm, cmd), daemon=True).start()

    def _update_stats(self):
        import psutil
        now = datetime.datetime.now().strftime("%I:%M %p")
        self._set_stat(self._time_label, "TIME", now)

        cpu = psutil.cpu_percent(interval=None)
        cpu_color = "#ff4444" if cpu > 80 else "#ffaa00" if cpu > 50 else "#00d4ff"
        self._set_stat(self._cpu_label, "CPU", f"{cpu:.0f}%", cpu_color)

        ram = psutil.virtual_memory().percent
        ram_color = "#ff4444" if ram > 85 else "#ffaa00" if ram > 65 else "#00d4ff"
        self._set_stat(self._ram_label, "RAM", f"{ram:.0f}%", ram_color)

        try:
            bat = psutil.sensors_battery()
            if bat:
                pct = int(bat.percent)
                plugged = "⚡" if bat.power_plugged else "🔋"
                bat_color = "#ff4444" if pct < 20 else "#ffaa00" if pct < 40 else "#00d4ff"
                self._set_stat(self._bat_label, "POWER", f"{plugged}{pct}%", bat_color)
        except:
            self._set_stat(self._bat_label, "POWER", "N/A")

    # ── WINDOW CONTROLS ──────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.MouseButton.RightButton:
            self.comm.speak.emit("Systems offline. Goodbye.")
            time.sleep(0.3)
            os._exit(0)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


# ─────────────────────────────────────────────
#  TTS ENGINE  (cross-platform)
# ─────────────────────────────────────────────
def _speak(text: str):
    safe = text.replace('"', '').replace("'", '').replace('`', '')
    if IS_LINUX and os.path.exists(PIPER_EXE):
        subprocess.Popen(
            f'echo "{safe}" | "{PIPER_EXE}" --model "{PIPER_MODEL}" '
            f'--output_raw | aplay -D default -r 22050 -f S16_LE -t raw 2>/dev/null',
            shell=True
        ).wait()
    elif IS_WINDOWS:
        subprocess.Popen(
            ['powershell', '-Command',
             f'Add-Type -AssemblyName System.Speech; '
             f'$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
             f'$s.Speak("{safe}")'],
            creationflags=subprocess.CREATE_NO_WINDOW
        ).wait()
    else:
        # macOS fallback
        subprocess.Popen(['say', safe]).wait()


# ─────────────────────────────────────────────
#  PERSISTENT LOG
# ─────────────────────────────────────────────
def _log(query: str):
    try:
        os.makedirs(NOTES_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {query}\n")
    except:
        pass


# ─────────────────────────────────────────────
#  CORE LOGIC
# ─────────────────────────────────────────────
def core_logic(comm: Communicate, raw: str):
    if not raw:
        return

    q = raw.lower().strip()
    _log(q)
    comm.update_log.emit(f"CMD → {q}")

    # ── TIME
    if any(w in q for w in ['time', 'what time']):
        t = datetime.datetime.now().strftime("%I:%M %p")
        comm.update_status.emit("Speaking")
        comm.speak.emit(f"The time is {t}, sir.")

    # ── DATE
    elif any(w in q for w in ['date', 'today', 'day is it']):
        d = datetime.datetime.now().strftime("%A, %B %d, %Y")
        comm.speak.emit(f"Today is {d}.")

    # ── BATTERY
    elif any(w in q for w in ['battery', 'power', 'charge']):
        try:
            import psutil
            bat = psutil.sensors_battery()
            if bat:
                plugged = "charging" if bat.power_plugged else "on battery"
                comm.speak.emit(f"Power level at {int(bat.percent)} percent, {plugged}.")
            else:
                # Linux fallback
                with open("/sys/class/power_supply/BAT0/capacity") as f:
                    lvl = f.read().strip()
                comm.speak.emit(f"Battery at {lvl} percent.")
        except Exception as e:
            comm.speak.emit("Power sensor unavailable.")

    # ── SYSTEM INFO
    elif any(w in q for w in ['system', 'cpu', 'ram', 'memory', 'performance', 'specs']):
        import psutil
        cpu  = psutil.cpu_percent(interval=1)
        ram  = psutil.virtual_memory()
        used = ram.used  // (1024**2)
        total= ram.total // (1024**2)
        comm.speak.emit(f"CPU at {cpu:.0f} percent. RAM usage {used} of {total} megabytes.")
        comm.update_log.emit(f"CPU:{cpu:.1f}%  RAM:{used}/{total}MB")

    # ── SCREENSHOT
    elif any(w in q for w in ['screenshot', 'snapshot', 'capture screen']):
        try:
            import pyautogui
            os.makedirs(SCREEN_DIR, exist_ok=True)
            comm.update_status.emit("Capturing")
            name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SCREEN_DIR, f"{name}.png")
            pyautogui.screenshot(path)
            comm.speak.emit("Screenshot captured and saved.")
            comm.update_log.emit(f"Saved → {path}")
        except Exception as e:
            comm.update_log.emit(f"Screenshot failed: {e}")
            comm.speak.emit("Screenshot failed.")

    # ── WIKIPEDIA
    elif any(w in q for w in ['wikipedia', 'search', 'who is', 'what is', 'tell me about']):
        term = q
        for word in ['wikipedia', 'search for', 'search', 'who is',
                     'what is', 'tell me about', WAKE_WORD]:
            term = term.replace(word, '')
        term = term.strip()
        if not term:
            comm.speak.emit("What would you like me to search for?")
            return
        comm.update_status.emit("Searching")
        comm.update_log.emit(f"Searching: {term}")
        try:
            import wikipedia
            summary = wikipedia.summary(term, sentences=2, auto_suggest=False)
            comm.speak.emit(f"According to records: {summary[:300]}")
            os.makedirs(NOTES_DIR, exist_ok=True)
            with open(NOTES_FILE, "a") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                f.write(f"\n## {term} ({ts})\n{summary}\n")
            comm.update_log.emit("Saved to study notes.")
        except Exception:
            comm.speak.emit(f"No record found for {term}.")

    # ── GOOGLE
    elif 'google' in q:
        term = q.replace('google', '').replace(WAKE_WORD, '').replace('search', '').strip()
        url  = f"https://www.google.com/search?q={term.replace(' ', '+')}"
        subprocess.Popen(["xdg-open" if IS_LINUX else "start", url],
                         shell=IS_WINDOWS)
        comm.speak.emit(f"Searching Google for {term}.")

    # ── YOUTUBE
    elif 'youtube' in q:
        term = q.replace('youtube', '').replace(WAKE_WORD, '').replace('search', '').strip()
        url  = f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}"
        subprocess.Popen(["xdg-open" if IS_LINUX else "start", url],
                         shell=IS_WINDOWS)
        comm.speak.emit(f"Opening YouTube for {term}.")

    # ── JOKE
    elif any(w in q for w in ['joke', 'funny', 'laugh']):
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
            "Why was the JavaScript developer sad? Because he didn't know how to 'null' his feelings.",
            "A SQL query walks into a bar, walks up to two tables and asks... can I join you?"
        ]
        import random
        comm.speak.emit(random.choice(jokes))

    # ── NOTES
    elif any(w in q for w in ['note', 'remember', 'write down']):
        content = q
        for w in ['note', 'remember', 'write down', 'take a note', WAKE_WORD]:
            content = content.replace(w, '')
        content = content.strip()
        if content:
            os.makedirs(NOTES_DIR, exist_ok=True)
            with open(NOTES_FILE, "a") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                f.write(f"\n- [{ts}] {content}\n")
            comm.speak.emit("Note saved, sir.")
            comm.update_log.emit(f"Note → {content}")
        else:
            comm.speak.emit("What would you like me to note?")

    # ── EXIT
    elif any(w in q for w in ['exit', 'offline', 'terminate', 'shutdown', 'goodbye', 'bye']):
        comm.update_status.emit("Offline")
        comm.update_log.emit("SHUTDOWN INITIATED")
        _speak("All systems going offline. Goodbye, sir.")
        time.sleep(2)
        os._exit(0)

    else:
        comm.update_log.emit("Command not recognized.")
        comm.update_status.emit("Standby")


# ─────────────────────────────────────────────
#  SENSOR LOOP — OFFLINE-FIRST VOSK + GOOGLE FALLBACK
# ─────────────────────────────────────────────
def sensor_loop(comm: Communicate):
    import pyaudio

    # ── Try loading Vosk
    vosk_available = False
    model = None
    try:
        import vosk
        vosk.SetLogLevel(-1)
        if os.path.exists(VOSK_MODEL_PATH):
            comm.update_status.emit("Loading")
            comm.update_log.emit("Loading Vosk model...")
            model = vosk.Model(VOSK_MODEL_PATH)
            vosk_available = True
            comm.update_log.emit("Vosk ready — offline STT active.")
            comm.update_status.emit("Standby")
        else:
            comm.update_log.emit("Vosk model not found — falling back to Google STT.")
    except ImportError:
        comm.update_log.emit("Vosk not installed — using Google STT.")

    # ── audio setup
    MIC_RATE  = 44100
    VOSK_RATE = 16000
    CHUNK     = 8192

    p = pyaudio.PyAudio()

    # find best input device
    device_index = 0
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0 and 'HDA' in str(info['name']):
            device_index = i
            break

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=MIC_RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
    except Exception as e:
        comm.update_log.emit(f"Mic open failed: {e}")
        comm.update_status.emit("ERROR")
        return

    comm.update_log.emit(f"Mic open on device {device_index}. Wake word: '{WAKE_WORD}'")

    # ── announce ready
    time.sleep(1)
    comm.speak.emit("Initialization complete. S.A.M.U.E.L. online. Say Samuel to activate.")
    comm.update_status.emit("Standby")
    comm.update_log.emit("Systems nominal. Awaiting activation.")

    # ── mode label
    comm.update_log.emit(f"STT mode: {'OFFLINE (Vosk)' if vosk_available else 'ONLINE (Google)'}")

    if vosk_available:
        _vosk_loop(comm, stream, model, MIC_RATE, VOSK_RATE, CHUNK)
    else:
        _google_loop(comm, stream, p, MIC_RATE, CHUNK)


def _vosk_loop(comm, stream, model, MIC_RATE, VOSK_RATE, CHUNK):
    import vosk
    import audioop

    rec = vosk.KaldiRecognizer(model, VOSK_RATE)
    awaiting_command = False
    state_ref = [None]   # mutable ref for ratecv state

    while True:
        try:
            comm.update_status.emit("Listening")
            data = stream.read(CHUNK, exception_on_overflow=False)

            # ── energy for reactor visualisation
            rms = _rms(data)
            comm.set_wave_level.emit(min(1.0, rms / 3000))

            # ── downsample 44100 → 16000
            data_down, state_ref[0] = audioop.ratecv(
                data, 2, 1, MIC_RATE, VOSK_RATE, state_ref[0])

            if rec.AcceptWaveform(data_down):
                result = json.loads(rec.Result())
                text   = result.get("text", "").strip()
                if not text:
                    continue

                comm.update_log.emit(f"Heard: {text}")

                if awaiting_command:
                    comm.update_status.emit("Analyzing")
                    core_logic(comm, text)
                    awaiting_command = False
                    rec.Reset()

                elif WAKE_WORD in text:
                    command = text.replace(WAKE_WORD, "").strip()
                    comm.update_status.emit("Analyzing")
                    if command:
                        core_logic(comm, command)
                    else:
                        comm.speak.emit("Yes, sir?")
                        awaiting_command = True
                    rec.Reset()

        except Exception as e:
            comm.update_log.emit(f"Sensor error: {e}")
            comm.update_status.emit("Standby")
            time.sleep(0.5)


def _google_loop(comm, stream, p_audio, MIC_RATE, CHUNK):
    """Fallback: Google STT via speech_recognition."""
    try:
        import speech_recognition as sr
    except ImportError:
        comm.update_log.emit("speech_recognition not installed. Voice unavailable.")
        return

    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True

    while True:
        try:
            comm.update_status.emit("Listening")
            with sr.Microphone() as source:
                audio = r.listen(source, timeout=None, phrase_time_limit=7)
            comm.update_status.emit("Analyzing")
            text = r.recognize_google(audio, language='en-NG').lower()
            comm.update_log.emit(f"Heard: {text}")
            if WAKE_WORD in text:
                command = text.replace(WAKE_WORD, "").strip()
                if command:
                    core_logic(comm, command)
                else:
                    comm.speak.emit("Yes, sir?")
        except Exception:
            comm.update_status.emit("Standby")
            time.sleep(0.3)


def _rms(data: bytes) -> float:
    """Root mean square of int16 audio for energy visualisation."""
    import struct
    count  = len(data) // 2
    shorts = struct.unpack(f"{count}h", data)
    if not shorts:
        return 0.0
    sq_sum = sum(s * s for s in shorts)
    return math.sqrt(sq_sum / count)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(NOTES_DIR,  exist_ok=True)
    os.makedirs(SCREEN_DIR, exist_ok=True)

    app  = QApplication(sys.argv)
    comm = Communicate()
    hud  = SamuelHUD(comm)

    # centre on screen
    screen = app.primaryScreen().geometry()
    hud.move(
        (screen.width()  - hud.width())  // 2,
        (screen.height() - hud.height()) // 2
    )
    hud.show()

    threading.Thread(target=sensor_loop, args=(comm,), daemon=True).start()
    sys.exit(app.exec())
