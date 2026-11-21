"""Settings for Crammphibian.

Everything can be overridden with environment variables so the tool works
with no config file at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # Where indexes are stored. One sub-folder per "collection" (e.g. a course).
    data_dir: Path = field(
        default_factory=lambda: Path(_env("CRAMMPHIBIAN_HOME", str(Path.home() / ".crammphibian")))
    )

    # Local models served by Ollama (https://ollama.com).
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://localhost:11434"))
    embed_model: str = field(default_factory=lambda: _env("CRAMMPHIBIAN_EMBED_MODEL", "nomic-embed-text"))
    llm_model: str = field(default_factory=lambda: _env("CRAMMPHIBIAN_LLM_MODEL", "llama3.2:3b"))

    # "ollama" (fully offline) or "openai" (any OpenAI-compatible API, needs OPENAI_API_KEY).
    llm_provider: str = field(default_factory=lambda: _env("CRAMMPHIBIAN_LLM_PROVIDER", "ollama"))
    openai_model: str = field(default_factory=lambda: _env("CRAMMPHIBIAN_OPENAI_MODEL", "gpt-4o-mini"))

    # Chunking and retrieval.
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 6

    def collection_dir(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "default"
        return self.data_dir / safe
