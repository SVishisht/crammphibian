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


def pick_embed_model(models: list[str] | None, configured: str) -> str:
    """Use the configured embedding model if it's downloaded, else any embedding model that is."""
    from .config import LITE_EMBED_MODEL, is_embed_model

    if not models or has_model(models, configured):
        return configured
    if has_model(models, LITE_EMBED_MODEL):
        return LITE_EMBED_MODEL
    return next((m for m in models if is_embed_model(m)), configured)


def pick_chat_models(models: list[str] | None, configured: str) -> list[str]:
    """Installed chat models with the configured one first (if present)."""
    from .config import is_embed_model

    chat = [m for m in (models or []) if not is_embed_model(m)]
    if not chat:
        return [configured]
    match = [m for m in chat if has_model([m], configured) or m == configured]
    return match + [m for m in chat if m not in match]
