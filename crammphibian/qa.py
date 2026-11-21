"""Retrieval-augmented answering with numbered citations."""

from __future__ import annotations

from collections.abc import Iterator

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .config import Settings

SYSTEM = """You are a study assistant helping a student prepare for exams.
Answer ONLY from the numbered course excerpts below. After each fact, cite the
excerpt it came from in square brackets, like [1] or [2][4].
If the excerpts don't contain the answer, say so plainly and suggest what to look
for instead. Do not make up facts, formulas or page numbers.
Be clear and well organised: short paragraphs or bullet points, define key terms,
and show worked steps for calculations.

Course excerpts:
{context}"""

PROMPT = ChatPromptTemplate.from_messages(
    [("system", SYSTEM), MessagesPlaceholder("history"), ("human", "{question}")]
)


def make_llm(settings: Settings, json_mode: bool = False, temperature: float = 0.1) -> BaseChatModel:
    """json_mode asks the model to reply with valid JSON (used for quizzes and flashcards)."""
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI  # optional extra: pip install "crammphibian[cloud]"

        kwargs = {"model_kwargs": {"response_format": {"type": "json_object"}}} if json_mode else {}
        return ChatOpenAI(model=settings.openai_model, temperature=temperature, **kwargs)
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_url,
        temperature=temperature,
        **({"format": "json"} if json_mode else {}),
    )


def format_context(docs: list[Document]) -> str:
    return "\n\n".join(f"[{i}] ({d.metadata['label']})\n{d.page_content}" for i, d in enumerate(docs, start=1))


def to_messages(history: list[tuple[str, str]], max_turns: int = 3) -> list:
    msgs = []
    for q, a in history[-max_turns:]:
        msgs += [HumanMessage(q), AIMessage(a)]
    return msgs


def stream_answer(
    llm: BaseChatModel,
    question: str,
    docs: list[Document],
    history: list[tuple[str, str]] | None = None,
) -> Iterator[str]:
    """Yield the answer text in pieces as the model writes it."""
    chain = PROMPT | llm | StrOutputParser()
    yield from chain.stream(
        {"context": format_context(docs), "question": question, "history": to_messages(history or [])}
    )


def search_query(question: str, history: list[tuple[str, str]] | None = None) -> str:
    """Follow-ups like "explain that more" search poorly on their own, so add the last question."""
    if history and len(question.split()) < 8:
        return f"{history[-1][0]} {question}"
    return question
