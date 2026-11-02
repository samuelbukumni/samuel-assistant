"""Look things up: Wikipedia summaries and the optional LLM fallback.

Wikipedia REST API: https://en.wikipedia.org/api/rest_v1/page/summary/{title}
OpenSearch (title lookup): https://en.wikipedia.org/w/api.php?action=opensearch
"""
from __future__ import annotations

import os
import random
import urllib.parse
from typing import Dict, List, Optional

import requests

HEADERS = {"User-Agent": "SAMUEL-assistant/5.0 (personal learning assistant; github.com/samuelbukumni/samuel-assistant)"}

JOKES = [   # kept from v4
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
    "Why was the JavaScript developer sad? Because he didn't know how to 'null' his feelings.",
    "A SQL query walks into a bar, walks up to two tables and asks... can I join you?",
]


def joke() -> str:
    return random.choice(JOKES)


def _summary(title: str) -> Optional[Dict]:
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
    r = requests.get(url, headers=HEADERS, timeout=8)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    if data.get("type") == "disambiguation" or not data.get("extract"):
        return None
    return {
        "title": data.get("title", title),
        "description": data.get("description", ""),
        "extract": data.get("extract", ""),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }


def _search_titles(query: str, limit: int = 3) -> List[str]:
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=HEADERS, timeout=8, params={
        "action": "opensearch", "search": query, "limit": limit, "namespace": 0, "format": "json"})
    r.raise_for_status()
    data = r.json()
    return data[1] if isinstance(data, list) and len(data) > 1 else []


def wiki_summary(query: str) -> Dict:
    """{'ok': True, title, description, extract, url} or {'ok': False, 'reason': ...}."""
    query = query.strip()
    if not query:
        return {"ok": False, "reason": "empty"}
    try:
        direct = _summary(query[:1].upper() + query[1:])
        if direct:
            return {"ok": True, **direct}
        for title in _search_titles(query):
            found = _summary(title)
            if found:
                return {"ok": True, **found}
        return {"ok": False, "reason": "not found"}
    except requests.RequestException as exc:
        return {"ok": False, "reason": "offline", "detail": str(exc)}


# ── optional LLM ──────────────────────────────────────────────────────
class LLM:
    """Off by default. 'ollama' talks to a local Ollama server
    (POST /api/chat, docs: github.com/ollama/ollama/blob/main/docs/api.md);
    'openai' talks to any OpenAI-compatible /chat/completions endpoint with a
    key read from an environment variable. Nothing here is ever required."""

    def __init__(self, settings):
        self.s = settings
        self.backend = (settings.llm_backend or "off").lower()

    @property
    def enabled(self) -> bool:
        if self.backend == "ollama":
            return True
        if self.backend == "openai":
            return bool(self.s.openai_base_url and self.s.openai_model and os.environ.get(self.s.llm_key_env))
        return False

    def label(self) -> str:
        if self.backend == "ollama":
            return f"OLLAMA · {self.s.ollama_model}"
        if self.backend == "openai":
            return f"API · {self.s.openai_model}" if self.enabled else "API · NO KEY"
        return "OFF"

    def ask(self, prompt: str, system: str, history: Optional[List[Dict]] = None, timeout: float = 60) -> Optional[str]:
        messages = [{"role": "system", "content": system}] + (history or [])[-6:] + [{"role": "user", "content": prompt}]
        try:
            if self.backend == "ollama":
                r = requests.post(self.s.ollama_url.rstrip("/") + "/api/chat", timeout=timeout, json={
                    "model": self.s.ollama_model, "messages": messages, "stream": False,
                    "options": {"temperature": 0.4, "num_predict": 220}})
                r.raise_for_status()
                return (r.json().get("message") or {}).get("content", "").strip() or None
            if self.backend == "openai" and self.enabled:
                r = requests.post(self.s.openai_base_url.rstrip("/") + "/chat/completions", timeout=timeout,
                                  headers={"Authorization": "Bearer " + os.environ[self.s.llm_key_env]},
                                  json={"model": self.s.openai_model, "messages": messages,
                                        "temperature": 0.4, "max_tokens": 300})
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip() or None
        except Exception:
            return None
        return None
