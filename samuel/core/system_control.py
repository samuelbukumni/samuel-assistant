"""Laptop control: open apps and sites, volume, brightness, lock screen.

Every action tries the common Linux tools in order and reports honestly
when none is installed. Voice can only launch programs from the small
allow-list below; it never runs arbitrary shell commands.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from typing import List, Optional, Sequence, Tuple

IS_LINUX = platform.system() == "Linux"

# friendly name -> candidate executables (first one installed wins)
APPS = {
    "terminal": ["x-terminal-emulator", "gnome-terminal", "xfce4-terminal", "mate-terminal", "konsole", "xterm"],
    "files": ["nemo", "nautilus", "thunar", "caja", "dolphin", "pcmanfm"],
    "file manager": ["nemo", "nautilus", "thunar", "caja", "dolphin", "pcmanfm"],
    "browser": ["firefox", "google-chrome", "chromium", "chromium-browser", "brave-browser"],
    "firefox": ["firefox"],
    "chrome": ["google-chrome", "chromium", "chromium-browser"],
    "code": ["code", "codium"],
    "vs code": ["code", "codium"],
    "vscode": ["code", "codium"],
    "editor": ["xed", "gedit", "gnome-text-editor", "mousepad", "kate", "pluma"],
    "text editor": ["xed", "gedit", "gnome-text-editor", "mousepad", "kate", "pluma"],
    "calculator": ["gnome-calculator", "mate-calc", "galculator", "kcalc", "qalculate-gtk"],
    "settings": ["cinnamon-settings", "gnome-control-center", "xfce4-settings-manager", "systemsettings"],
    "system monitor": ["gnome-system-monitor", "mate-system-monitor", "xfce4-taskmanager", "ksysguard"],
    "task manager": ["gnome-system-monitor", "mate-system-monitor", "xfce4-taskmanager"],
    "music": ["rhythmbox", "audacious", "spotify", "vlc"],
    "vlc": ["vlc"],
    "spotify": ["spotify"],
    "libreoffice": ["libreoffice"],
    "writer": ["lowriter", "libreoffice"],
    "spreadsheet": ["localc", "libreoffice"],
    "camera": ["cheese", "guvcview"],
}

SITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "wikipedia": "https://en.wikipedia.org",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "netflix": "https://www.netflix.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "maps": "https://www.google.com/maps",
    "google maps": "https://www.google.com/maps",
    "reddit": "https://www.reddit.com",
    "chatgpt": "https://chatgpt.com",
    "khan academy": "https://www.khanacademy.org",
    "coursera": "https://www.coursera.org",
}

_DOMAIN_RE = re.compile(r"^(?:https?://)?([a-z0-9\-]+\.)+[a-z]{2,}(?:/\S*)?$")


def _spawn(args: Sequence[str]) -> bool:
    try:
        subprocess.Popen(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def _run(args: Sequence[str], timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        out = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
        return out.returncode == 0, (out.stdout or out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def open_url(url: str) -> bool:
    if IS_LINUX and shutil.which("xdg-open"):
        return _spawn(["xdg-open", url])
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def resolve_target(target: str) -> Tuple[str, Optional[str], Optional[List[str]]]:
    """Classify an 'open X' target -> (kind, url, command)."""
    t = target.lower().strip().rstrip(".")
    t = re.sub(r"^(the|my)\s+", "", t)
    t = re.sub(r"\s+(app|application|website|site|page)$", "", t)
    if t in SITES:
        return "site", SITES[t], None
    if _DOMAIN_RE.match(t.replace(" dot ", ".")):
        t = t.replace(" dot ", ".")
        return "site", t if t.startswith("http") else "https://" + t, None
    if t in APPS:
        for exe in APPS[t]:
            if shutil.which(exe):
                return "app", None, [exe]
        return "missing", None, None
    return "unknown", None, None


def open_target(target: str) -> Tuple[bool, str]:
    kind, url, cmd = resolve_target(target)
    if kind == "site":
        return open_url(url), f"Opening {url.split('//', 1)[-1]}."
    if kind == "app":
        return _spawn(cmd), f"Launching {target}."
    if kind == "missing":
        return False, f"I couldn't find a {target} program installed."
    return False, f"I don't know how to open {target} yet."


def web_search(engine: str, query: str) -> Tuple[bool, str]:
    q = urllib.parse.quote_plus(query)
    url = {"youtube": f"https://www.youtube.com/results?search_query={q}",
           "google": f"https://www.google.com/search?q={q}"}[engine]
    return open_url(url), f"Searching {engine.capitalize()} for {query}."


# ── volume ────────────────────────────────────────────────────────────
def volume(action: str, value: Optional[int] = None) -> Tuple[bool, str]:
    if shutil.which("pactl"):
        sink = "@DEFAULT_SINK@"
        cmd = {
            "up": ["pactl", "set-sink-volume", sink, "+10%"],
            "down": ["pactl", "set-sink-volume", sink, "-10%"],
            "mute": ["pactl", "set-sink-mute", sink, "1"],
            "unmute": ["pactl", "set-sink-mute", sink, "0"],
            "set": ["pactl", "set-sink-volume", sink, f"{value}%"],
        }.get(action)
        if cmd:
            ok, _ = _run(cmd)
            if ok:
                level = current_volume()
                suffix = f" Volume at {level} percent." if level is not None and action not in ("mute",) else ""
                return True, {"mute": "Muted.", "unmute": "Sound restored."}.get(action, "Done.") + suffix
        level = current_volume()
        if level is not None:
            return True, f"Volume is at {level} percent."
    if shutil.which("amixer"):
        arg = {"up": "10%+", "down": "10%-", "mute": "mute", "unmute": "unmute", "set": f"{value}%"}.get(action)
        if arg:
            ok, _ = _run(["amixer", "-q", "-D", "pulse", "sset", "Master", arg])
            if not ok:
                ok, _ = _run(["amixer", "-q", "sset", "Master", arg])
            if ok:
                return True, "Done."
    return False, "I can't reach the audio mixer. Install pulseaudio-utils for pactl."


def current_volume() -> Optional[int]:
    if not shutil.which("pactl"):
        return None
    ok, out = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    m = re.search(r"(\d+)%", out) if ok else None
    return int(m.group(1)) if m else None


# ── brightness ────────────────────────────────────────────────────────
def brightness(action: str, value: Optional[int] = None) -> Tuple[bool, str]:
    if shutil.which("brightnessctl"):
        arg = {"up": "+10%", "down": "10%-", "set": f"{value}%"}[action]
        ok, _ = _run(["brightnessctl", "-q", "set", arg])
        if ok:
            return True, "Brightness adjusted."
    if shutil.which("xbacklight"):
        args = {"up": ["-inc", "10"], "down": ["-dec", "10"], "set": ["-set", str(value)]}[action]
        ok, _ = _run(["xbacklight", *args])
        if ok:
            return True, "Brightness adjusted."
    return False, "No brightness control found. Install brightnessctl (sudo apt install brightnessctl)."


# ── session ───────────────────────────────────────────────────────────
def lock_screen() -> Tuple[bool, str]:
    for cmd in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"],
                ["cinnamon-screensaver-command", "--lock"], ["gnome-screensaver-command", "--lock"]):
        if shutil.which(cmd[0]):
            ok, _ = _run(cmd)
            if ok:
                return True, "Locking the screen."
    return False, "I couldn't find a screen locker."


def screenshot_fallback(path: str) -> bool:
    for cmd in (["gnome-screenshot", "-f", path], ["scrot", path], ["grim", path],
                ["import", "-window", "root", path]):
        if shutil.which(cmd[0]):
            ok, _ = _run(cmd, timeout=10)
            if ok and os.path.exists(path):
                return True
    return False


def notify(title: str, text: str) -> None:
    if shutil.which("notify-send"):
        _spawn(["notify-send", "-a", "S.A.M.U.E.L.", title, text])
