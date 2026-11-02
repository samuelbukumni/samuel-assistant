"""Settings and paths.

Settings live in ~/.config/samuel/config.json (override with SAMUEL_CONFIG).
Any key you leave out keeps its default, so the file can be tiny, e.g.

    {"weather_city": "London", "persona": "friday"}

Secrets are never read from this file. The optional cloud LLM key is read
from the environment variable named by `llm_key_env`.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional

HOME = Path.home()


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


VOICE_DIR = _env_path("SAMUEL_VOICE_DIR", HOME / "samuel_voice")
CONFIG_FILE = _env_path("SAMUEL_CONFIG", HOME / ".config" / "samuel" / "config.json")
DATA_DIR = _env_path("SAMUEL_DATA_DIR", HOME / ".local" / "share" / "samuel")
NOTES_DIR = HOME / "Documents" / "SAMUEL_Notes"          # same as v4
SCREEN_DIR = HOME / "Documents" / "SAMUEL_Screenshots"   # same as v4


@dataclass
class Settings:
    # Who S.A.M.U.E.L. serves
    user_name: str = "Samuel"
    honorific_jarvis: str = "sir"
    honorific_friday: str = "boss"
    persona: str = "jarvis"                      # "jarvis" or "friday"

    # Voice input (Vosk). Saying a persona's name also switches to it.
    wake_words: List[str] = field(default_factory=lambda: ["samuel", "jarvis", "friday"])
    vosk_model: str = str(VOICE_DIR / "vosk-model-small-en-in-0.4")
    mic_device_hint: str = "HDA"                 # v4 picked the first input whose name contains this

    # Voice output (Piper). Voices must exist on huggingface.co/rhasspy/piper-voices.
    piper_exe: str = str(VOICE_DIR / "piper" / "piper")
    voice_jarvis: str = str(VOICE_DIR / "piper" / "en_GB-alan-medium.onnx")
    voice_friday: str = str(VOICE_DIR / "piper" / "en_GB-jenny_dioco-medium.onnx")
    audio_player: str = "aplay"

    # Weather (Open-Meteo, no key). Off until a city or coordinates are set.
    weather_city: str = ""
    weather_lat: Optional[float] = None
    weather_lon: Optional[float] = None

    # Optional LLM fallback for questions no built-in skill handles. Off by default.
    llm_backend: str = "off"                     # "off" | "ollama" | "openai"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:0.5b"
    openai_base_url: str = ""                    # any OpenAI-compatible /v1 endpoint
    openai_model: str = ""
    llm_key_env: str = "SAMUEL_LLM_API_KEY"      # name of the env var holding the key

    # HUD
    fps: int = 30
    idle_fps: int = 15
    lite: bool = False          # older laptops: no radar sweep or bloom, 20/10 fps
    start_fullscreen: bool = False
    boot_sequence: bool = True

    # Storage
    notes_dir: str = str(NOTES_DIR)
    screenshot_dir: str = str(SCREEN_DIR)
    data_dir: str = str(DATA_DIR)

    # Filled in by load_settings, not saved
    load_error: str = ""

    def honorific(self, persona: str) -> str:
        return self.honorific_friday if persona == "friday" else self.honorific_jarvis

    def voice_for(self, persona: str) -> str:
        return self.voice_friday if persona == "friday" else self.voice_jarvis


def load_settings(path: Optional[Path] = None) -> Settings:
    """Read the JSON config, ignoring unknown keys. A broken file never stops startup."""
    settings = Settings()
    path = Path(path) if path else CONFIG_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return settings
    except (OSError, ValueError) as exc:
        settings.load_error = f"Could not read {path}: {exc}"
        return settings
    if not isinstance(raw, dict):
        settings.load_error = f"{path} must contain a JSON object"
        return settings
    known = {f.name for f in fields(Settings)} - {"load_error"}
    for key, value in raw.items():
        if key in known:
            setattr(settings, key, value)
    return settings


def write_example_config(path: Path) -> Path:
    """Write every setting with its default so it is easy to edit.
    Never overwrites an existing file."""
    path = Path(path)
    if path.exists():
        raise SystemExit(f"{path} already exists; edit it or delete it first.")
    data = asdict(Settings())
    data.pop("load_error", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
