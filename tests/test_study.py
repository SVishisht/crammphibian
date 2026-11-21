import csv
import io
import json

import pytest
from langchain_core.language_models import FakeListChatModel

from crammphibian.config import Settings
from crammphibian.index import StudyIndex
from crammphibian.ollama_check import pick_chat_models, pick_embed_model
from crammphibian.study import cards_to_csv, make_cards, make_quiz, parse_json, parse_quiz, stream_summary

from .conftest import HashEmbeddings


@pytest.fixture
def index(tmp_path, course_files):
    idx = StudyIndex("BIO", Settings(data_dir=tmp_path / "data"), embeddings=HashEmbeddings())
    for f in course_files:
        idx.add_file(f)
    return idx


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    assert parse_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_quiz_parsing_maps_answers_and_sources(index):
    docs = index.search("Krebs cycle", k=2)
    reply = json.dumps(
        {
            "questions": [
                {"question": "Where does the Krebs cycle run?",
                 "options": ["Cytoplasm", "Mitochondrial matrix", "Nucleus", "Ribosome"],
                 "answer": "Mitochondrial matrix", "explanation": "See lecture.", "source": 1},
                {"question": "Letter answer", "options": ["A) x", "B) y", "C) z", "D) w"], "answer": "C"},
                {"question": "Broken: answer not in options", "options": ["a", "b"], "answer": "zzz"},
                {"question": "", "options": ["a", "b"], "answer": "a"},
            ]
        }
    )
    qs = parse_quiz(reply, docs)
    assert len(qs) == 2  # broken items are dropped
    assert qs[0].answer == 1 and qs[0].source == "Biology Lecture 3.pdf, p. 2"
    assert qs[1].answer == 2 and qs[1].source == ""


def test_make_quiz_and_cards_end_to_end(index):
    docs = index.sample(4)
    quiz_llm = FakeListChatModel(responses=[json.dumps([
        {"question": "Q?", "options": ["1", "2", "3", "4"], "answer": 0, "explanation": "e", "source": "2"}
    ])])
    qs = make_quiz(quiz_llm, "", docs, n=3)
    assert len(qs) == 1 and qs[0].source == docs[1].metadata["label"]

    card_llm = FakeListChatModel(responses=['{"cards": [{"front": "ATP", "back": "Energy, made in the ETC", "source": 1}]}'])
    cards = make_cards(card_llm, "energy", docs)
    assert cards[0].front == "ATP"
    rows = list(csv.reader(io.StringIO(cards_to_csv(cards))))
    assert rows[0][0] == "ATP" and docs[0].metadata["label"] in rows[0][1]


def test_summary_streams(index):
    llm = FakeListChatModel(responses=["## Key ideas\n- Glycolysis is in the cytoplasm [1]"])
    out = "".join(stream_summary(llm, "", index.sample(3)))
    assert "Key ideas" in out


def test_sample_spreads_across_files(index):
    picked = index.sample(3)
    assert len(picked) == 3
    assert {d.metadata["source"] for d in picked} == {"Biology Lecture 3.pdf", "Econ Week 5.pptx"}
    only = index.sample(10, sources=["Econ Week 5.pptx"])
    assert only and all(d.metadata["source"] == "Econ Week 5.pptx" for d in only)


def test_course_keeps_its_embedding_model(tmp_path, course_files, monkeypatch):
    s = Settings(data_dir=tmp_path / "data", embed_model="all-minilm")
    idx = StudyIndex("BIO", s, embeddings=HashEmbeddings())
    idx.add_file(course_files[0])

    seen = {}
    monkeypatch.setattr(
        "crammphibian.index.default_embeddings", lambda st: seen.setdefault("m", st.embed_model) and HashEmbeddings()
    )
    later = StudyIndex("BIO", Settings(data_dir=tmp_path / "data", embed_model="nomic-embed-text"))
    assert seen["m"] == "all-minilm" and later.embed_model == "all-minilm"
    assert later.search("Krebs", k=1)


def test_model_pickers():
    assert pick_embed_model(None, "nomic-embed-text") == "nomic-embed-text"
    assert pick_embed_model(["nomic-embed-text:latest", "llama3.2:3b"], "nomic-embed-text") == "nomic-embed-text"
    assert pick_embed_model(["all-minilm:latest", "qwen2.5:0.5b"], "nomic-embed-text") == "all-minilm"
    assert pick_embed_model(["mxbai-embed-large:latest"], "nomic-embed-text") == "mxbai-embed-large:latest"

    assert pick_chat_models(["all-minilm:latest", "qwen2.5:0.5b", "llama3.2:3b"], "llama3.2:3b") == [
        "llama3.2:3b", "qwen2.5:0.5b"
    ]
    assert pick_chat_models([], "llama3.2:3b") == ["llama3.2:3b"]
