"""Speech-to-text: Vosk offline, with v4's Google fallback. Both optional.

If pyaudio, Vosk or the model is missing, the listener reports why and the
HUD keeps working with typed commands.

Flow: always listen for a wake word ("samuel", "jarvis", "friday"). A phrase
that starts with it is executed straight away ("samuel what time is it");
the wake word alone arms a command window of ~8 s. Push-to-talk (the mic
button or Ctrl+Space) arms the same window without a wake word.
While the assistant is speaking, recognition results are ignored so it
doesn't answer itself.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from samuel.voice.audio import level, resample

VOSK_RATE = 16000
COMMAND_WINDOW = 8.0


class Listener:
    def __init__(self, bus, settings, on_command: Callable[[str, str], None]):
        self.bus = bus
        self.s = settings
        self.on_command = on_command
        self.status = "starting"
        self.detail = ""
        self._armed_until = 0.0
        self._speaking = False
        self._running = True
        bus.speaking.connect(self._on_speaking)

    # called from GUI thread
    def arm(self) -> None:
        if self.status not in ("vosk", "google"):
            self.bus.log.emit("warn", f"Voice input is offline ({self.detail}). Type your command instead.")
            return
        self._armed_until = time.monotonic() + COMMAND_WINDOW
        self.bus.listening.emit(True)

    def start(self) -> None:
        threading.Thread(target=self._run, name="stt", daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def _on_speaking(self, speaking: bool) -> None:
        self._speaking = speaking

    def _report(self, status: str, detail: str) -> None:
        self.status, self.detail = status, detail
        self.bus.voice_status.emit({"stt": status, "stt_detail": detail})

    # ── main loop ───────────────────────────────────────────────────
    def _run(self) -> None:
        try:
            import pyaudio
        except ImportError:
            self._report("offline", "pyaudio not installed")
            return
        model = None
        try:
            import vosk
            vosk.SetLogLevel(-1)
            if os.path.isdir(self.s.vosk_model):
                self.bus.log.emit("sys", "Loading Vosk speech model…")
                model = vosk.Model(self.s.vosk_model)
        except ImportError:
            vosk = None
        except Exception as exc:
            self.bus.log.emit("warn", f"Vosk model failed to load: {exc}")
            model = None

        pa = pyaudio.PyAudio()
        device = self._pick_device(pa)
        stream, rate = self._open(pa, pyaudio, device)
        if stream is None:
            self._report("offline", "no microphone could be opened")
            return
        if model is not None:
            self._report("vosk", f"offline · {os.path.basename(self.s.vosk_model)}")
            self._vosk_loop(vosk, model, stream, rate)
        else:
            stream.stop_stream()
            stream.close()
            self._google_loop()

    def _pick_device(self, pa) -> Optional[int]:
        hint = (self.s.mic_device_hint or "").lower()
        first = None
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
            except Exception:
                continue
            if info.get("maxInputChannels", 0) > 0:
                first = i if first is None else first
                if hint and hint in str(info.get("name", "")).lower():
                    return i
        return first

    def _open(self, pa, pyaudio, device):
        for rate in (VOSK_RATE, 44100, 48000):
            try:
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                                 input_device_index=device, frames_per_buffer=int(rate * 0.25))
                return stream, rate
            except Exception:
                continue
        return None, 0

    def _handle_text(self, text: str) -> None:
        text = text.strip().lower()
        if not text:
            return
        wakes = [w.lower() for w in self.s.wake_words]
        armed = time.monotonic() < self._armed_until
        first = text.split()[0]
        if armed or first in wakes or any(text.startswith(w + " ") for w in wakes):
            self._armed_until = 0.0
            self.bus.listening.emit(False)
            self.bus.heard.emit(text, True)
            self.on_command(text, "voice")
        elif any(w in text.split() for w in wakes):
            # wake word in the middle: "okay samuel ..." -> keep from the wake word on
            words = text.split()
            idx = min(words.index(w) for w in wakes if w in words)
            self.bus.heard.emit(" ".join(words[idx:]), True)
            self.on_command(" ".join(words[idx:]), "voice")

    def _vosk_loop(self, vosk, model, stream, rate) -> None:
        rec = vosk.KaldiRecognizer(model, VOSK_RATE)
        chunk = int(rate * 0.25)
        last_partial = ""
        while self._running:
            try:
                data = stream.read(chunk, exception_on_overflow=False)
            except Exception as exc:
                self.bus.log.emit("warn", f"Microphone read error: {exc}")
                time.sleep(0.5)
                continue
            if self._armed_until and time.monotonic() > self._armed_until:
                self._armed_until = 0.0
                self.bus.listening.emit(False)
            if self._speaking:
                rec.Reset()
                if self._armed_until:
                    self._armed_until += 0.25     # the window starts after the reply
                continue
            self.bus.energy.emit(level(data))
            pcm = resample(data, rate, VOSK_RATE) if rate != VOSK_RATE else data
            if rec.AcceptWaveform(pcm):
                text = json.loads(rec.Result()).get("text", "")
                last_partial = ""
                self._handle_text(text)
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "")
                if partial and partial != last_partial and time.monotonic() < self._armed_until:
                    self.bus.heard.emit(partial, False)
                last_partial = partial

    def _google_loop(self) -> None:
        try:
            import speech_recognition as sr
        except ImportError:
            self._report("offline", "no Vosk model and SpeechRecognition not installed")
            return
        self._report("google", "online fallback (Vosk model not found)")
        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True
        while self._running:
            try:
                if self._speaking:
                    time.sleep(0.2)
                    continue
                with sr.Microphone() as source:
                    audio = r.listen(source, timeout=None, phrase_time_limit=7)
                if self._speaking:
                    continue
                text = r.recognize_google(audio, language="en-NG").lower()
                self._handle_text(text)
            except Exception:
                time.sleep(0.3)
