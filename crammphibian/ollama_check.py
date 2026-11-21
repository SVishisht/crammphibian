"""Tiny helpers to tell the student what's missing instead of showing a stack trace."""

from __future__ import annotations

import json
import urllib.request


def installed_models(url: str, timeout: float = 2.0) -> list[str] | None:
    """Model names Ollama has pulled, or None if Ollama isn't running."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout) as r:
            data = json.load(r)
    except Exception:
        return None
    return [m.get("name", "") for m in data.get("models", [])]


def has_model(models: list[str], wanted: str) -> bool:
    """'nomic-embed-text' matches 'nomic-embed-text:latest'."""
    base = wanted if ":" in wanted else wanted + ":latest"
    return any(m == wanted or m == base for m in models)
