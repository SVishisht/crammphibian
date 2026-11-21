import pytest
from langchain_core.language_models import FakeListChatModel

from studysearch.config import Settings
from studysearch.index import StudyIndex
from studysearch.loaders import UnsupportedFile, load_file
from studysearch.qa import format_context, search_query, stream_answer

from .conftest import HashEmbeddings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data")


def test_loaders_keep_page_and_slide_numbers(course_files):
    pdf, pptx = course_files
    pages = load_file(pdf)
    assert [d.metadata["number"] for d in pages] == [1, 2, 3]
    assert pages[1].metadata["label"] == "Biology Lecture 3.pdf, p. 2"
    assert "Krebs" in pages[1].page_content

    slides = load_file(pptx)
    assert [d.metadata["label"] for d in slides] == ["Econ Week 5.pptx, slide 1", "Econ Week 5.pptx, slide 2"]
    assert "Speaker notes" in slides[1].page_content  # notes are searchable too


def test_old_ppt_gives_helpful_error(tmp_path):
    f = tmp_path / "old.ppt"
    f.write_bytes(b"x")
    with pytest.raises(UnsupportedFile, match="Save As"):
        load_file(f)


def test_index_search_and_citations(settings, course_files):
    pdf, pptx = course_files
    idx = StudyIndex("BIO", settings, embeddings=HashEmbeddings())
    assert idx.add_file(pdf)["status"] == "indexed"
    assert idx.add_file(pptx)["status"] == "indexed"
    assert idx.add_file(pdf)["status"] == "skipped"  # duplicate

    top = idx.search("where does the citric acid cycle happen?", k=2)
    assert top[0].metadata["label"] == "Biology Lecture 3.pdf, p. 2"

    top = idx.search("what is price elasticity", k=1)
    assert top[0].metadata["label"] == "Econ Week 5.pptx, slide 2"

    # Filtering to one file.
    only = idx.search("cycle", k=5, sources=["Econ Week 5.pptx"])
    assert only and all(d.metadata["source"] == "Econ Week 5.pptx" for d in only)


def test_index_persists_and_removes(settings, course_files):
    pdf, pptx = course_files
    idx = StudyIndex("BIO", settings, embeddings=HashEmbeddings())
    idx.add_file(pdf)
    idx.add_file(pptx)

    again = StudyIndex("BIO", settings, embeddings=HashEmbeddings())
    assert set(again.files) == {"Biology Lecture 3.pdf", "Econ Week 5.pptx"}
    assert again.search("ATP electron transport", k=1)[0].metadata["number"] == 3

    again.remove_file("Biology Lecture 3.pdf")
    assert all(d.metadata["source"] == "Econ Week 5.pptx" for d in again.search("Krebs cycle", k=5))
    again.remove_file("Econ Week 5.pptx")
    assert again.is_empty() and again.search("anything") == []
    assert StudyIndex("BIO", settings, embeddings=HashEmbeddings()).is_empty()


def test_answer_prompt_has_numbered_sources(settings, course_files):
    pdf, _ = course_files
    idx = StudyIndex("BIO", settings, embeddings=HashEmbeddings())
    idx.add_file(pdf)
    docs = idx.search("Krebs cycle", k=2)
    ctx = format_context(docs)
    assert ctx.startswith("[1] (Biology Lecture 3.pdf, p. 2)")

    llm = FakeListChatModel(responses=["It happens in the mitochondrial matrix [1]."])
    answer = "".join(stream_answer(llm, "Where is the Krebs cycle?", docs))
    assert "[1]" in answer


def test_follow_up_questions_borrow_context():
    hist = [("Explain the Krebs cycle", "...")]
    assert "Krebs" in search_query("more detail please", hist)
    assert search_query("What is the role of NADH in the electron transport chain?", hist).startswith("What")
