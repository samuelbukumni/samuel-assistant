"""Wires everything together: settings → bus → brain/voice threads → HUD.

    python -m samuel                 normal start (voice if available)
    python -m samuel --demo          scripted tour, no mic/speaker, throwaway data
    python -m samuel --no-voice      keyboard only
    python -m samuel --write-config  create ~/.config/samuel/config.json and exit
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from samuel import __version__, personas
from samuel.config import CONFIG_FILE, load_settings, write_example_config
from samuel.core.brain import Brain
from samuel.core.bus import Bus
from samuel.core.telemetry import Telemetry, human_duration, top_processes
from samuel.ui.theme import load_fonts
from samuel.core.bus import thread_target


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="samuel", description="S.A.M.U.E.L. v5 — JARVIS/FRIDAY learning HUD")
    ap.add_argument("--demo", action="store_true", help="scripted tour with simulated voice; uses a temporary data folder")
    ap.add_argument("--no-voice", action="store_true", help="disable microphone and speech output")
    ap.add_argument("--no-boot", action="store_true", help="skip the boot animation")
    ap.add_argument("--lite", action="store_true", help="lighter rendering for old laptops (no sweep/bloom, 20/10 fps)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--persona", choices=["jarvis", "friday"])
    ap.add_argument("--size", default="", help="window size, e.g. 1600x900")
    ap.add_argument("--config", default="", help=f"settings file (default {CONFIG_FILE})")
    ap.add_argument("--write-config", action="store_true", help="write an example settings file and exit")
    ap.add_argument("--version", action="version", version=f"S.A.M.U.E.L. {__version__}")
    return ap.parse_args(argv)


class NetProbe:
    """Cheap connectivity check (TCP connect to a public DNS server) every 60 s."""

    def __init__(self, bus):
        self.bus = bus
        threading.Thread(target=thread_target(self._run), name="net", daemon=True).start()

    def _run(self):
        while True:
            ok = False
            for host in ("1.1.1.1", "8.8.8.8"):
                try:
                    socket.create_connection((host, 53), timeout=2).close()
                    ok = True
                    break
                except OSError:
                    continue
            self.bus.voice_status.emit({"net": ok})
            time.sleep(60)


class Samuel:
    def __init__(self, args, qt_app):
        self.args = args
        self.qt = qt_app
        s = load_settings(Path(args.config) if args.config else None)
        if args.persona:
            s.persona = args.persona
        if args.lite:
            s.lite = True
        if s.lite:
            from samuel.ui import paint
            paint.GLOW["passes"] = 0
            s.fps, s.idle_fps = min(s.fps, 20), min(s.idle_fps, 10)
        self.demo = args.demo
        if self.demo:
            tmp = Path(tempfile.mkdtemp(prefix="samuel-demo-"))
            s.data_dir = str(tmp)
            s.notes_dir = str(tmp / "notes")
            s.screenshot_dir = str(tmp / "screens")
        self.s = s
        self.t0 = time.time()
        self.proc = psutil.Process()
        self.fonts = load_fonts()
        self.bus = Bus()
        self.telemetry = Telemetry()
        self.brain = Brain(self.bus, s)
        self.voice_off = args.no_voice or self.demo

        from samuel.voice.tts import Speaker
        self.speaker = Speaker(self.bus, s, force_silent=self.voice_off)
        self.listener = None
        if not self.voice_off:
            from samuel.voice.stt import Listener
            self.listener = Listener(self.bus, s, self.brain.submit)

        from samuel.ui.hud import Hud
        self.hud = Hud(s, s.persona, boot=s.boot_sequence and not args.no_boot, checks=self._boot_checks(),
                       demo=self.demo)
        self.hud.reactor.lite = s.lite
        self.status = {"stt": ("DEMO" if self.demo else "OFF" if self.voice_off else "STARTING", "off"),
                       "net": ("CHECKING", "off")}
        self._wire()
        self._refresh_status()
        if s.load_error:
            self.bus.log.emit("warn", f"Settings file ignored: {s.load_error}")

    # ------------------------------------------------------------------ setup
    def _boot_checks(self):
        s = self.s
        fonts_ok = self.fonts.get("ui") == "Rajdhani"
        checks = [("DISPLAY TYPEFACES", "3 LOADED" if fonts_ok else "SYSTEM FALLBACK", "ok" if fonts_ok else "warn")]
        sp = self.speaker
        checks.append(("SPEECH SYNTHESIS", {"piper": "PIPER · NEURAL", "espeak": "ESPEAK"}.get(sp.backend, "SILENT"),
                       {"piper": "ok", "espeak": "warn"}.get(sp.backend, "off")))
        if self.voice_off:
            checks.append(("SPEECH RECOGNITION", "DISABLED" if not self.demo else "DEMO · SIMULATED", "off"))
        else:
            model = os.path.isdir(s.vosk_model)
            mic = importlib.util.find_spec("pyaudio") is not None
            checks.append(("SPEECH RECOGNITION", "VOSK · OFFLINE" if (model and mic) else
                           "NO MIC LIBRARY" if not mic else "NO VOSK MODEL", "ok" if model and mic else "warn"))
        vm = psutil.virtual_memory()
        checks.append(("TELEMETRY", f"{psutil.cpu_count()} CORES · {vm.total / 2**30:.1f} GB", "ok"))
        checks.append(("LEARNING STORE", "SQLITE · SM-2", "ok"))
        from samuel.core.knowledge import LLM
        llm = LLM(s)
        checks.append(("LANGUAGE MODEL", llm.label() if s.llm_backend != "off" else "OFF · RULES ENGINE",
                       "ok" if llm.enabled else "off"))
        checks.append(("PERSONA", personas.get_persona(s.persona).callsign, "ok"))
        return checks

    def _wire(self):
        b, h = self.bus, self.hud
        b.log.connect(h.on_log)
        b.say.connect(h.on_say)
        b.say.connect(self.speaker.speak)
        b.heard.connect(h.on_heard)
        b.busy.connect(h.on_busy)
        b.speaking.connect(h.on_speaking)
        b.listening.connect(h.on_listening)
        b.energy.connect(h.on_energy)
        b.persona.connect(self._on_persona)
        b.learning.connect(h.learning.stats.set_stats)
        b.lesson.connect(h.learning.lesson.set_lesson)
        b.card.connect(h.on_card)
        b.reminders.connect(h.ops.view.set_reminders)
        b.alert.connect(h.on_alert)
        b.weather.connect(h.ops.view.set_weather)
        b.voice_status.connect(self._on_status)
        b.ui.connect(self._on_ui)
        h.command.connect(self.brain.submit)
        h.action.connect(self._on_action)
        self.timer = QTimer()
        self.timer.timeout.connect(self._second)
        self.timer.start(1000)

    def start(self):
        size = self.args.size
        if size and "x" in size:
            w, hh = (int(v) for v in size.lower().split("x"))
        else:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            w, hh = max(1180, int(geo.width() * 0.92)), max(700, int(geo.height() * 0.92))
        self.hud.resize(w, hh)
        if self.args.fullscreen or self.s.start_fullscreen:
            self.hud.showFullScreen()
        else:
            self.hud.show()
        self.hud.clock.start()
        self.brain.start()
        if self.listener:
            self.listener.start()
        NetProbe(self.bus)
        if self.demo:
            self.bus.weather.emit(demo_weather())
        self._second()
        if self.hud.boot_overlay is None:
            self._on_action("booted", None)

    # ------------------------------------------------------------------ slots
    def _second(self):
        sample = self.telemetry.sample()
        self.hud.telemetry.update_sample(sample)
        self._ticks = getattr(self, "_ticks", -1) + 1
        if self._ticks % 3 == 0:                      # process list is the priciest probe: every 3 s
            self.hud.telemetry.procs.set_rows(top_processes(5))
        self.hud.second()
        rss = self.proc.memory_info().rss / 2**20
        self.hud.reactor.set_callouts([
            ("VOICE IN", self.status["stt"][0]),
            ("VOICE OUT", self._tts_text()[0]),
            ("SESSION", human_duration(time.time() - self.t0)),
            ("FOOTPRINT", f"{rss:.0f} MB RAM"),
        ])

    def _tts_text(self):
        sp = self.speaker
        if sp.backend == "piper":
            voice = os.path.basename(self.s.voice_for(sp.persona)).split("-")[1].upper() if "-" in sp.detail else "PIPER"
            return f"PIPER · {voice}", "ok"
        if sp.backend == "espeak":
            return "ESPEAK", "warn"
        return ("SIMULATED" if self.demo else "SILENT"), "off"

    def _refresh_status(self):
        h = self.hud
        h.set_status("stt", *self.status["stt"])
        h.set_status("tts", *self._tts_text())
        h.set_status("net", *self.status["net"])
        from samuel.core.knowledge import LLM
        llm = LLM(self.s)
        h.set_status("llm", llm.label() if self.s.llm_backend != "off" else "OFF", "ok" if llm.enabled else "off")

    def _on_status(self, d: dict):
        if "stt" in d:
            st = d["stt"]
            self.status["stt"] = {"vosk": ("VOSK", "ok"), "google": ("GOOGLE", "warn")}.get(st, ("TEXT ONLY", "off"))
            if st == "offline":
                self.bus.log.emit("warn", f"Voice input offline: {d.get('stt_detail', '')}. Type commands below.")
            elif st in ("vosk", "google"):
                self.bus.log.emit("sys", f"Voice input ready ({d.get('stt_detail', '')}). Say “Samuel” to wake me.")
        if "net" in d:
            self.status["net"] = ("ONLINE", "ok") if d["net"] else ("OFFLINE", "warn")
        self._refresh_status()

    def _on_persona(self, key: str):
        self.hud.on_persona(key)
        self.speaker.set_persona(key)
        self._refresh_status()

    def _on_ui(self, name: str, arg):
        if name == "arm_listen":
            self._on_action("listen", None)
        elif name == "stop_speaking":
            self.speaker.stop()
        elif name == "quit":
            QTimer.singleShot(int((arg or 0) * 1000), self.quit)
        elif name == "screenshot":
            self._on_action("screenshot", None)
        elif name in ("fullscreen", "windowed", "minimize"):
            self.hud.window_action(name)
        elif name == "demo":
            self._on_action("demo", None)

    def _on_action(self, name: str, arg):
        if name == "listen":
            if self.listener:
                self.listener.arm()
            else:
                self.bus.log.emit("warn", "Voice input is off in this session. Type your command below.")
        elif name == "persona":
            key = personas.other(self.hud.persona.key).key if arg == "toggle" else arg
            self.brain.call("persona", key)
        elif name in ("answer", "grade"):
            self.brain.call(name, arg)
        elif name in ("reveal", "reveal_or_next"):
            self.brain.call(name)
        elif name == "stop_speaking":
            self.speaker.stop()
        elif name == "screenshot":
            path = self.hud.save_screenshot(Path(self.s.screenshot_dir))
            self.bus.log.emit("sys", f"Screenshot saved: {path}")
        elif name == "demo":
            from samuel.demo import DemoDriver
            if not getattr(self, "_demo", None) or not self._demo.running:
                self._demo = DemoDriver(self)
                self._demo.start()
        elif name == "booted":
            self.brain.call("boot_greeting")
            if self.demo:
                QTimer.singleShot(4500, lambda: self._on_action("demo", None))
        elif name == "quit":
            self.quit()

    def quit(self):
        if self.listener:
            self.listener.stop()
        self.speaker.stop()
        self.timer.stop()
        self.hud.clock.pause()
        self.qt.quit()


def demo_weather() -> dict:
    return {"ok": True, "place": "Demo data · simulated", "temp": 24.0, "feels": 26.0, "humidity": 71, "wind": 9,
            "code": 2, "text": "Partly cloudy", "is_day": True, "high": 29.0, "low": 21.0, "rain_chance": 20,
            "time": time.time(), "demo": True}


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.write_config:
        path = write_example_config(Path(args.config) if args.config else CONFIG_FILE)
        print(f"Settings written to {path}")
        return 0
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("S.A.M.U.E.L.")
    app.setApplicationVersion(__version__)
    samuel = Samuel(args, app)
    samuel.start()
    app._samuel = samuel          # keep a reference
    code = app.exec()
    samuel.quit()
    return code
