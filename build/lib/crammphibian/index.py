"""A per-collection search index: semantic (FAISS vectors) + keyword (BM25),
merged with reciprocal rank fusion.

Why hybrid: embeddings find passages that *mean* the same thing as the
question, BM25 catches exact terms (formula names, acronyms, people) that
small local embedding models sometimes miss.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import Settings
from .loaders import load_file

MANIFEST = "manifest.json"


def file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def default_embeddings(settings: Settings) -> Embeddings:
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_url)


class StudyIndex:
    def __init__(self, name: str, settings: Settings | None = None, embeddings: Embeddings | None = None):
        self.settings = settings or Settings()
        self.name = name
        self.dir = self.settings.collection_dir(name)
        # A course must keep using the embedding model it was built with, otherwise
        # the stored vectors and new queries won't match. Read that first.
        mpath = self.dir / MANIFEST
        if mpath.exists():
            saved = json.loads(mpath.read_text()).get("embed_model")
            if saved and embeddings is None:
                self.settings = replace(self.settings, embed_model=saved)
        self.embeddings = embeddings or default_embeddings(self.settings)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size, chunk_overlap=self.settings.chunk_overlap
        )
        self._vs = None
        self._bm25 = None
        self._chunks: list[Document] = []
        self.manifest: dict = {"embed_model": self.settings.embed_model, "files": {}}
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        mpath = self.dir / MANIFEST
        if not mpath.exists():
            return
        self.manifest = json.loads(mpath.read_text())
        if (self.dir / "index.faiss").exists():
            from langchain_community.vectorstores import FAISS

            self._vs = FAISS.load_local(
                str(self.dir), self.embeddings, allow_dangerous_deserialization=True  # our own file
            )
            self._chunks = list(self._vs.docstore._dict.values())
            self._build_bm25()

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self._vs is not None:
            self._vs.save_local(str(self.dir))
        (self.dir / MANIFEST).write_text(json.dumps(self.manifest, indent=2))

    def _build_bm25(self) -> None:
        if not self._chunks:
            self._bm25 = None
            return
        from langchain_community.retrievers import BM25Retriever

        self._bm25 = BM25Retriever.from_documents(self._chunks)

    # ---------- building ----------
    @property
    def files(self) -> dict:
        return self.manifest["files"]

    def is_empty(self) -> bool:
        return not self._chunks

    def add_file(self, path: str | Path, display_name: str | None = None) -> dict:
        """Index one file. Returns a small report dict. Skips files already indexed."""
        path = Path(path)
        name = display_name or path.name
        digest = file_hash(path)
        if any(info["sha256"] == digest for info in self.files.values()):
            return {"file": name, "status": "skipped", "reason": "already indexed"}
        if name in self.files:  # same name, new content: replace the old version
            self.remove_file(name)

        pages = load_file(path, name)
        if not pages:
            return {
                "file": name,
                "status": "empty",
                "reason": "no text found (scanned PDFs or image-only slides need OCR, not supported yet)",
            }
        chunks = self.splitter.split_documents(pages)
        for c in chunks:
            c.metadata["file_id"] = digest[:16]

        from langchain_community.vectorstores import FAISS

        if self._vs is None:
            self._vs = FAISS.from_documents(chunks, self.embeddings)
        else:
            self._vs.add_documents(chunks)
        self._chunks.extend(chunks)
        self._build_bm25()

        kind = pages[0].metadata["kind"]
        self.files[name] = {"sha256": digest, "units": len(pages), "kind": kind, "chunks": len(chunks)}
        self._save()
        return {"file": name, "status": "indexed", "units": len(pages), "kind": kind, "chunks": len(chunks)}

    def remove_file(self, name: str) -> None:
        info = self.files.pop(name, None)
        if info is None or self._vs is None:
            return
        fid = info["sha256"][:16]
        ids = [k for k, d in self._vs.docstore._dict.items() if d.metadata.get("file_id") == fid]
        if ids:
            self._vs.delete(ids)
        self._chunks = list(self._vs.docstore._dict.values())
        if not self._chunks:
            self._vs = None
            for f in ("index.faiss", "index.pkl"):
                (self.dir / f).unlink(missing_ok=True)
        self._build_bm25()
        self._save()

    def delete(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        self._vs, self._bm25, self._chunks = None, None, []
        self.manifest = {"embed_model": self.settings.embed_model, "files": {}}

    @property
    def embed_model(self) -> str:
        return self.manifest.get("embed_model", self.settings.embed_model)

    def sample(self, n: int, sources: list[str] | None = None) -> list[Document]:
        """Up to n chunks spread evenly through the selected files (for whole-file summaries/quizzes)."""
        pool = [d for d in self._chunks if not sources or d.metadata.get("source") in sources]
        pool.sort(key=lambda d: (d.metadata.get("source", ""), d.metadata.get("number", 0)))
        if len(pool) <= n:
            return pool
        step = len(pool) / n
        return [pool[int(i * step)] for i in range(n)]

    # ---------- searching ----------
    def search(self, query: str, k: int | None = None, sources: list[str] | None = None) -> list[Document]:
        """Hybrid search. `sources` limits results to those file names."""
        if self.is_empty():
            return []
        k = k or self.settings.top_k
        pool = max(k * 4, 20)

        def allowed(d: Document) -> bool:
            return not sources or d.metadata.get("source") in sources

        filt = (lambda md: md.get("source") in sources) if sources else None
        vec = self._vs.similarity_search(query, k=pool, filter=filt, fetch_k=pool * 5)
        self._bm25.k = pool * 3 if sources else pool
        kw = [d for d in self._bm25.invoke(query) if allowed(d)][:pool]

        # Reciprocal rank fusion (k=60 is the standard constant).
        scores: dict[tuple, float] = {}
        docs: dict[tuple, Document] = {}
        for ranked in (vec, kw):
            for rank, d in enumerate(ranked):
                key = (d.metadata.get("file_id"), d.metadata.get("number"), d.page_content[:80])
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
                docs.setdefault(key, d)
        best = sorted(scores, key=scores.get, reverse=True)[:k]
        return [docs[key] for key in best]
