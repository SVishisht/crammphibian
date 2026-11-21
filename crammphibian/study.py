"""Exam-prep modes on top of retrieval: summaries, multiple-choice quizzes, flashcards.

Every generated item points back to an excerpt number, which we map to the
file + page/slide label so students can check the source.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .qa import format_context

# ---------------------------------------------------------------- summaries

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You turn course material into exam revision notes.
Use ONLY the numbered excerpts. Cite excerpts in square brackets like [2] after each point.
Write in Markdown with these sections:
## Key ideas
(5-10 bullet points, the most exam-relevant first)
## Key terms
(term: one-line definition)
## Formulas and processes
(only if the excerpts contain any; skip this section otherwise)
## Likely exam questions
(3-5 questions a lecturer might ask)

Excerpts:
{context}""",
        ),
        ("human", "Make revision notes on: {topic}"),
    ]
)


def stream_summary(llm: BaseChatModel, topic: str, docs: list[Document]) -> Iterator[str]:
    chain = SUMMARY_PROMPT | llm | StrOutputParser()
    yield from chain.stream({"context": format_context(docs), "topic": topic or "the whole material"})


# ---------------------------------------------------------------- JSON helpers


def parse_json(text: str):
    """Parse JSON from a model reply, tolerating ```json fences and chatter around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("The model didn't return valid JSON. Try again or pick a bigger model.")


def _items(data, key: str) -> list:
    if isinstance(data, dict):
        data = data.get(key, next((v for v in data.values() if isinstance(v, list)), []))
    return data if isinstance(data, list) else []


def _source_label(ref, docs: list[Document]) -> str:
    try:
        n = int(str(ref).strip("[] "))
        return docs[n - 1].metadata["label"]
    except (ValueError, IndexError, TypeError):
        return ""


# ---------------------------------------------------------------- quiz


@dataclass
class Question:
    question: str
    options: list[str]
    answer: int  # index into options
    explanation: str
    source: str  # "file, p. N"


QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You write multiple-choice exam questions from course material.
Use ONLY facts in the numbered excerpts. Each question has exactly 4 options and one correct answer.
Make wrong options plausible. Vary difficulty. Don't repeat questions.
Reply with JSON only, in exactly this shape:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "answer": "the correct option text", "explanation": "why, in one or two sentences", "source": 1}}]}}
"source" is the excerpt number the answer comes from.

Excerpts:
{context}""",
        ),
        ("human", "Write {n} questions about: {topic}"),
    ]
)


def _answer_index(raw, options: list[str]) -> int | None:
    if isinstance(raw, int) and 0 <= raw < len(options):
        return raw
    s = str(raw).strip()
    if len(s) == 1 and s.upper() in "ABCD":
        i = "ABCD".index(s.upper())
        return i if i < len(options) else None
    norm = lambda x: re.sub(r"^[A-Da-d][).:]\s*", "", x).strip().lower()  # noqa: E731
    for i, o in enumerate(options):
        if norm(o) == norm(s):
            return i
    return None


def parse_quiz(text: str, docs: list[Document]) -> list[Question]:
    out: list[Question] = []
    for q in _items(parse_json(text), "questions"):
        if not isinstance(q, dict):
            continue
        opts = [str(o).strip() for o in q.get("options", []) if str(o).strip()]
        ans = _answer_index(q.get("answer"), opts)
        if not q.get("question") or len(opts) < 2 or ans is None:
            continue  # small models sometimes produce broken items; skip rather than show nonsense
        out.append(
            Question(
                question=str(q["question"]).strip(),
                options=opts,
                answer=ans,
                explanation=str(q.get("explanation", "")).strip(),
                source=_source_label(q.get("source"), docs),
            )
        )
    return out


def make_quiz(llm: BaseChatModel, topic: str, docs: list[Document], n: int = 5) -> list[Question]:
    chain = QUIZ_PROMPT | llm | StrOutputParser()
    text = chain.invoke({"context": format_context(docs), "topic": topic or "the whole material", "n": n})
    return parse_quiz(text, docs)[:n]


# ---------------------------------------------------------------- flashcards


@dataclass
class Card:
    front: str
    back: str
    source: str


CARDS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You make study flashcards from course material.
Use ONLY facts in the numbered excerpts. Front: a short question or term. Back: a concise answer (1-3 sentences).
Reply with JSON only, in exactly this shape:
{{"cards": [{{"front": "...", "back": "...", "source": 1}}]}}
"source" is the excerpt number the card comes from.

Excerpts:
{context}""",
        ),
        ("human", "Make {n} flashcards about: {topic}"),
    ]
)


def parse_cards(text: str, docs: list[Document]) -> list[Card]:
    out = []
    for c in _items(parse_json(text), "cards"):
        if isinstance(c, dict) and c.get("front") and c.get("back"):
            out.append(Card(str(c["front"]).strip(), str(c["back"]).strip(), _source_label(c.get("source"), docs)))
    return out


def make_cards(llm: BaseChatModel, topic: str, docs: list[Document], n: int = 10) -> list[Card]:
    chain = CARDS_PROMPT | llm | StrOutputParser()
    text = chain.invoke({"context": format_context(docs), "topic": topic or "the whole material", "n": n})
    return parse_cards(text, docs)[:n]


def cards_to_csv(cards: list[Card]) -> str:
    """Two columns (front, back) plus source: imports straight into Anki or Quizlet."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for c in cards:
        back = f"{c.back} ({c.source})" if c.source else c.back
        w.writerow([c.front, back])
    return buf.getvalue()
