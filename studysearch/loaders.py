"""Turn PDFs and PowerPoints into LangChain Documents.

Each Document is one PDF page or one slide, so every answer can cite
"file, page N" or "file, slide N".
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".pptx"}


class UnsupportedFile(ValueError):
    pass


def load_file(path: str | Path, display_name: str | None = None) -> list[Document]:
    """Load one file. `display_name` is what citations show (defaults to the file name)."""
    path = Path(path)
    name = display_name or path.name
    ext = Path(name).suffix.lower() or path.suffix.lower()
    if ext == ".pdf":
        return _load_pdf(path, name)
    if ext == ".pptx":
        return _load_pptx(path, name)
    if ext == ".ppt":
        raise UnsupportedFile(
            f"{name}: old .ppt format isn't supported. Open it in PowerPoint/Keynote/"
            "LibreOffice and 'Save As' .pptx (or export to PDF), then add it again."
        )
    raise UnsupportedFile(f"{name}: only .pdf and .pptx files are supported.")


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\x00", "").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _load_pdf(path: Path, name: str) -> list[Document]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    docs: list[Document] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = _clean(page.extract_text() or "")
        except Exception as exc:  # a single bad page shouldn't sink the file
            log.warning("Could not read %s page %d: %s", name, i, exc)
            continue
        if text:
            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": name, "kind": "page", "number": i, "label": f"{name}, p. {i}"},
                )
            )
    return docs


def _shape_text(shape) -> list[str]:
    out: list[str] = []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        out.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            out.append(" | ".join(cell.text for cell in row.cells))
    # Grouped shapes hold more shapes inside them.
    if hasattr(shape, "shapes"):
        for sub in shape.shapes:
            out.extend(_shape_text(sub))
    return out


def _load_pptx(path: Path, name: str) -> list[Document]:
    from pptx import Presentation

    prs = Presentation(str(path))
    docs: list[Document] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            parts.extend(_shape_text(shape))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text if slide.notes_slide.notes_text_frame else ""
            if notes.strip():
                parts.append("Speaker notes: " + notes)
        text = _clean("\n".join(parts))
        if text:
            docs.append(
                Document(
                    page_content=text,
                    metadata={"source": name, "kind": "slide", "number": i, "label": f"{name}, slide {i}"},
                )
            )
    return docs
