"""Text-to-speech with Piper, plus a silent mode so the HUD still animates.

Backends, tried in order:
  piper   ~/samuel_voice/piper/piper (the 2023 release binary v4 uses) or a
          `piper` command from `pip install piper-tts`. Audio is streamed
          through Python into `aplay`, so the reactor reacts to the real
          loudness of each word.
  espeak  espeak-ng / espeak if installed (robotic, but offline)
  silent  no audio: the reply is shown as subtitles and the visualiser
          plays a simulated envelope for the same duration.

Text is passed on stdin, never through a shell, so quotes in replies are safe.
"""
from __future__ import annotations

import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import threading
import time
from typing import Optional

from samuel.voice.audio import level
from samuel.core.bus import thread_target


def _sample_rate(model: str, default: int = 22050) -> int:
    try:
        with open(model + ".json", encoding="utf-8") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except (OSError, ValueError, KeyError, TypeError):
        return default


class Speaker:
    def __init__(self, bus, settings, force_silent: bool = False):
        self.bus = bus
        self.s = settings
        self.force_silent = force_silent
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._stop = threading.Event()
        self._procs = []
        self.backend = "silent"
        self.detail = ""
        self.persona = settings.persona
        self._piper_flag = "--output_raw"
        self._detect()
        threading.Thread(target=thread_target(self._worker), name="tts", daemon=True).start()

    # ── detection ────────────────────────────────────────────────────
    def _piper_exe(self) -> Optional[str]:
        if os.path.isfile(self.s.piper_exe) and os.access(self.s.piper_exe, os.X_OK):
            return self.s.piper_exe
        return shutil.which("piper")

    def _detect(self) -> None:
        if self.force_silent:
            self.backend, self.detail = "silent", "demo mode"
            return
        exe = self._piper_exe()
        player = shutil.which(self.s.audio_player)
        if exe and player and os.path.isfile(self.s.voice_for(self.persona)):
            self.backend, self.detail = "piper", os.path.basename(self.s.voice_for(self.persona))
            try:
                help_text = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=10)
                text = help_text.stdout + help_text.stderr
                if "--output-raw" in text and "--output_raw" not in text:
                    self._piper_flag = "--output-raw"
            except (OSError, subprocess.SubprocessError):
                pass
            return
        missing = []
        if not exe:
            missing.append("piper")
        if not player:
            missing.append(self.s.audio_player)
        if exe and not os.path.isfile(self.s.voice_for(self.persona)):
            missing.append(os.path.basename(self.s.voice_for(self.persona)))
        for espeak in ("espeak-ng", "espeak"):
            if shutil.which(espeak):
                self.backend, self.detail = "espeak", f"{espeak} (missing: {', '.join(missing)})"
                self._espeak = espeak
                return
        self.backend, self.detail = "silent", "missing: " + ", ".join(missing)

    def set_persona(self, key: str) -> None:
        self.persona = key
        if not self.force_silent:
            self._detect()

    # ── public ───────────────────────────────────────────────────────
    def speak(self, text: str) -> None:
        text = re.sub(r"[\x00-\x1f]+", " ", text or "").strip()
        if text:
            self._q.put((text, self.persona))

    def stop(self) -> None:
        self._stop.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        for p in list(self._procs):
            try:
                p.kill()
            except OSError:
                pass

    # ── worker ───────────────────────────────────────────────────────
    def _worker(self) -> None:
        while True:
            text, persona = self._q.get()
            self._stop.clear()
            self.bus.speaking.emit(True)
            try:
                if self.backend == "piper":
                    ok = self._piper(text, persona)
                    if not ok:
                        self._simulate(text)
                elif self.backend == "espeak":
                    self._espeak_say(text)
                else:
                    self._simulate(text)
            except Exception as exc:   # never let audio kill the assistant
                self.bus.log.emit("warn", f"Voice output error: {exc}")
                self._simulate(text)
            finally:
                self.bus.energy.emit(0.0)
                if self._q.empty():
                    self.bus.speaking.emit(False)

    def _piper(self, text: str, persona: str) -> bool:
        model = self.s.voice_for(persona)
        if not os.path.isfile(model):
            model = self.s.voice_jarvis
        rate = _sample_rate(model)
        synth = subprocess.Popen([self._piper_exe(), "--model", model, self._piper_flag],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        play = subprocess.Popen([shutil.which(self.s.audio_player) or self.s.audio_player, "-q", "-r", str(rate),
                                 "-f", "S16_LE", "-t", "raw", "-c", "1"],
                                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._procs = [synth, play]
        try:
            synth.stdin.write(text.encode("utf-8") + b"\n")
            synth.stdin.close()
            chunk = rate // 15 * 2          # ~66 ms of audio
            got_audio = False
            while not self._stop.is_set():
                data = synth.stdout.read(chunk)
                if not data:
                    break
                got_audio = True
                self.bus.energy.emit(level(data))
                play.stdin.write(data)
            play.stdin.close()
            if self._stop.is_set():
                play.kill()
            play.wait(timeout=30)
            return got_audio
        except (BrokenPipeError, OSError, subprocess.SubprocessError):
            return False
        finally:
            for p in (synth, play):
                if p.poll() is None:
                    p.kill()
            self._procs = []

    def _espeak_say(self, text: str) -> None:
        p = subprocess.Popen([self._espeak, "-s", "165", "--stdin"], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._procs = [p]
        p.stdin.write(text.encode("utf-8"))
        p.stdin.close()
        t0 = time.monotonic()
        while p.poll() is None and not self._stop.is_set():
            self.bus.energy.emit(_envelope(time.monotonic() - t0))
            time.sleep(1 / 30)
        if p.poll() is None:
            p.kill()
        self._procs = []

    def _simulate(self, text: str) -> None:
        """No audio device or voice: animate for as long as reading it would take."""
        words = max(1, len(text.split()))
        duration = min(14.0, max(1.2, words / 2.7))
        t0 = time.monotonic()
        while not self._stop.is_set():
            t = time.monotonic() - t0
            if t >= duration:
                break
            self.bus.energy.emit(_envelope(t) * min(1.0, (duration - t) * 3))
            time.sleep(1 / 30)


_rng = random.Random(7)


def _envelope(t: float) -> float:
    """Speech-like loudness: syllables (~5 Hz) inside phrases (~0.6 Hz)."""
    syllable = 0.5 + 0.5 * math.sin(t * 2 * math.pi * 4.7 + math.sin(t * 3.1) * 2)
    phrase = 0.55 + 0.45 * math.sin(t * 2 * math.pi * 0.55)
    return max(0.0, min(1.0, 0.18 + 0.75 * syllable * phrase + _rng.uniform(-0.06, 0.06)))
