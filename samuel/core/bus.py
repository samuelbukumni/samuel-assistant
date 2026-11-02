"""Qt signals that connect the worker threads (brain, voice) to the HUD.

Background threads only ever emit these signals; Qt delivers them to the
GUI thread, so widgets are never touched from another thread.
"""
from PyQt6.QtCore import QObject, pyqtSignal


class Bus(QObject):
    log = pyqtSignal(str, str)          # kind ("user" | "ai" | "sys" | "warn" | "err"), text
    say = pyqtSignal(str)               # a reply to show as subtitle and speak
    heard = pyqtSignal(str, bool)       # live transcript, is_final
    busy = pyqtSignal(bool)             # brain is working on a command
    speaking = pyqtSignal(bool)
    listening = pyqtSignal(bool)        # awaiting a command after the wake word
    energy = pyqtSignal(float)          # 0..1 voice level (mic or TTS)
    persona = pyqtSignal(str)           # "jarvis" | "friday"
    learning = pyqtSignal(dict)         # stats snapshot for the learning panel
    lesson = pyqtSignal(dict)           # active lesson {title, point, index, total} or {}
    card = pyqtSignal(dict)             # active quiz question / flashcard or {}
    reminders = pyqtSignal(list)        # upcoming reminders [{id, text, due, kind}]
    alert = pyqtSignal(str, str)        # title, text  (reminder fired, etc.)
    weather = pyqtSignal(dict)
    voice_status = pyqtSignal(dict)     # {"stt": "...", "tts": "...", "llm": "..."}
    ui = pyqtSignal(str, object)        # HUD actions: fullscreen, minimize, quit, screenshot
