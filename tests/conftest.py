import hashlib
import re

import pytest
from langchain_core.embeddings import Embeddings


class HashEmbeddings(Embeddings):
    """Deterministic bag-of-words embeddings so tests run without Ollama."""

    dim = 256

    def _vec(self, text):
        v = [0.0] * self.dim
        for w in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def make_pdf(path, pages):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for text in pages:
        y = 720
        for line in text.split("\n"):
            c.drawString(72, y, line)
            y -= 16
        c.showPage()
    c.save()


def make_pptx(path, slides):
    from pptx import Presentation

    prs = Presentation()
    for title, body, notes in slides:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = title
        s.placeholders[1].text = body
        if notes:
            s.notes_slide.notes_text_frame.text = notes
    prs.save(str(path))


@pytest.fixture
def course_files(tmp_path):
    pdf = tmp_path / "Biology Lecture 3.pdf"
    make_pdf(
        pdf,
        [
            "Cell Respiration\nGlycolysis happens in the cytoplasm.\nIt splits glucose into two pyruvate molecules.",
            "The Krebs cycle\nAlso called the citric acid cycle.\nIt runs in the mitochondrial matrix and makes NADH and FADH2.",
            "Electron transport chain\nOxidative phosphorylation produces most of the ATP, about 34 molecules.",
        ],
    )
    pptx = tmp_path / "Econ Week 5.pptx"
    make_pptx(
        pptx,
        [
            ("Supply and Demand", "Equilibrium price is where supply equals demand.", ""),
            ("Elasticity", "Price elasticity of demand = % change in quantity / % change in price.",
             "Remember: elastic means the absolute value is greater than 1."),
        ],
    )
    return pdf, pptx
