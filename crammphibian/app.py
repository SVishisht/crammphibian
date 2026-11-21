"""Streamlit UI. Run with:  crammphibian   (or: streamlit run crammphibian/app.py)"""

from __future__ import annotations

import random
import tempfile
from dataclasses import replace
from pathlib import Path

import streamlit as st

from crammphibian.config import Settings
from crammphibian.index import StudyIndex
from crammphibian.loaders import UnsupportedFile
from crammphibian.ollama_check import has_model, installed_models, pick_chat_models, pick_embed_model
from crammphibian.qa import make_llm, search_query, stream_answer
from crammphibian.study import cards_to_csv, make_cards, make_quiz, stream_summary

MASCOT = Path(__file__).with_name("assets") / "mascot.png"
AVATAR = str(MASCOT) if MASCOT.exists() else "🐸"

st.set_page_config(page_title="Crammphibian", page_icon=AVATAR, layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 2rem; max-width: 1100px;}
    [data-testid="stSidebar"] h1 {font-size: 1.6rem;}
    .cr-card {border: 1px solid rgba(63,163,77,.35); border-radius: 12px; padding: 1rem 1.2rem;
              margin-bottom: .75rem; background: rgba(63,163,77,.06);}
    .cr-src {opacity: .7; font-size: .85rem;}
    </style>""",
    unsafe_allow_html=True,
)
if MASCOT.exists():
    st.logo(str(MASCOT), size="large")

settings = Settings()
TIPS = [
    "Hop to it! Add your slides and lecture PDFs.",
    "Tip: Quiz me works best on one lecture at a time.",
    "Tip: open Sources to see the exact page each answer came from.",
    "Tip: export flashcards to Anki or Quizlet as CSV.",
]


def collections() -> list[str]:
    if not settings.data_dir.exists():
        return []
    return sorted(p.name for p in settings.data_dir.iterdir() if (p / "manifest.json").exists())


@st.cache_resource(show_spinner=False)
def get_index(name: str, embed_model: str) -> StudyIndex:
    return StudyIndex(name, replace(settings, embed_model=embed_model))


# ---------------- sidebar: course, model, files ----------------
models = installed_models(settings.ollama_url)

with st.sidebar:
    st.title("🐸 Crammphibian" if not MASCOT.exists() else "Crammphibian")
    st.caption("Your offline exam study buddy")

    existing = collections()
    choice = st.selectbox("Course", existing + ["➕ New course…"], index=0)
    if choice == "➕ New course…" or not existing:
        course = st.text_input("Course name", placeholder="e.g. BIO 101").strip()
    else:
        course = choice

    with st.expander("⚙️ Model", expanded=models is None):
        use_cloud = st.toggle(
            "Use cloud model (OpenAI API key)",
            value=settings.llm_provider == "openai",
            help="Off = fully offline with Ollama. Your files and search always stay local; with this on, "
            "your question and the matching excerpts are sent to the API.",
        )
        settings.llm_provider = "openai" if use_cloud else "ollama"
        if use_cloud:
            settings.openai_model = st.text_input("Cloud model", settings.openai_model)
        else:
            settings.llm_model = st.selectbox("Local model", pick_chat_models(models, settings.llm_model))
        settings.top_k = st.slider("Passages per answer", 3, 12, settings.top_k)

    if models is None:
        st.error("Ollama isn't running. Open the Ollama app, then refresh this page.")

if not course:
    st.markdown("## 🐸 Welcome to Crammphibian")
    st.markdown(
        "Load your lecture PDFs and PowerPoints, then **ask questions**, get **revision notes**, "
        "**quiz yourself** and make **flashcards**, all cited to the exact page or slide, "
        "and all on your own computer.\n\n👈 Start by naming a course in the sidebar (e.g. *BIO 101*)."
    )
    st.stop()

embed_for_new = pick_embed_model(models, settings.embed_model)
index = get_index(course, embed_for_new)

# Health checks, in plain words.
with st.sidebar:
    if models is not None:
        needed = [index.embed_model] + ([] if use_cloud else [settings.llm_model])
        for m in needed:
            if not has_model(models, m):
                st.warning(f"Model `{m}` isn't downloaded. In a terminal run:\n\n`ollama pull {m}`")

    st.divider()
    st.subheader("📚 Files")
    uploads = st.file_uploader(
        "Add PDFs or PowerPoints", type=["pdf", "pptx"], accept_multiple_files=True, key=f"up-{course}"
    )
    if uploads and st.button("Add to course", type="primary", use_container_width=True):
        progress = st.progress(0.0)
        for n, up in enumerate(uploads, start=1):
            progress.progress((n - 1) / len(uploads), text=f"Reading {up.name}…")
            with tempfile.NamedTemporaryFile(suffix=Path(up.name).suffix, delete=False) as tmp:
                tmp.write(up.getbuffer())
            try:
                rep = index.add_file(tmp.name, display_name=up.name)
                if rep["status"] == "indexed":
                    n_u = rep["units"]
                    unit = ("page" if rep["kind"] == "page" else "slide") + ("" if n_u == 1 else "s")
                    st.success(f"{up.name}: {n_u} {unit}")
                else:
                    st.info(f"{up.name}: {rep['reason']}")
            except UnsupportedFile as e:
                st.error(str(e))
            except Exception as e:  # most often: Ollama not running / model missing
                st.error(f"{up.name}: {e}")
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        progress.empty()

    if index.files:
        for fname, info in index.files.items():
            n = info["units"]
            unit = ("page" if info["kind"] == "page" else "slide") + ("" if n == 1 else "s")
            st.caption(f"📄 {fname} · {n} {unit}")
        with st.expander("Manage files"):
            to_remove = st.selectbox("File", list(index.files), key=f"rmsel-{course}")
            if st.button("Remove this file", use_container_width=True):
                index.remove_file(to_remove)
                st.rerun()
            st.divider()
            if st.button(f"Delete course “{course}”", use_container_width=True):
                index.delete()
                get_index.clear()
                for k in [k for k in st.session_state if k.endswith(f"-{course}")]:
                    del st.session_state[k]
                st.rerun()
            st.caption(f"Search model: `{index.embed_model}`")

# ---------------- main area ----------------
st.header(course)
if index.is_empty():
    st.info(f"🐸 {TIPS[0]} Use the sidebar, then come back here.")
    st.stop()

mode = st.segmented_control(
    "Mode", ["💬 Ask", "📝 Notes", "🧠 Quiz me", "🃏 Flashcards"], default="💬 Ask", key=f"mode-{course}",
    label_visibility="collapsed",
) or "💬 Ask"
only = st.multiselect("Files to use", list(index.files), placeholder="All files")
sources = only or None


def show_sources(docs, label="Sources"):
    with st.expander(f"{label} ({len(docs)})"):
        for i, d in enumerate(docs, start=1):
            st.markdown(f"**[{i}] {d.metadata['label']}**")
            text = d.page_content
            st.caption(text[:700] + ("…" if len(text) > 700 else ""))


def gather(topic: str, k: int) -> list:
    """Topic given: best matching passages. No topic: a spread across the selected files."""
    return index.search(topic, k=k, sources=sources) if topic.strip() else index.sample(k, sources=sources)


def llm_error(e: Exception):
    st.error(f"🐸 The model couldn't finish ({e}). Check that Ollama is running, or try another model.")


# ---- Ask ----
if mode == "💬 Ask":
    search_only = st.toggle("Search only (just show the best passages, no AI answer)", value=False)
    history: list[dict] = st.session_state.setdefault(f"chat-{course}", [])
    if not history:
        st.caption(random.choice(TIPS[1:]))
    for turn in history:
        with st.chat_message("user"):
            st.markdown(turn["q"])
        with st.chat_message("assistant", avatar=AVATAR):
            st.markdown(turn["a"])
            show_sources(turn["docs"])

    question = st.chat_input("Ask about your notes, e.g. “Explain the Krebs cycle step by step”")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        pairs = [(t["q"], t["a"]) for t in history]
        with st.chat_message("assistant", avatar=AVATAR):
            try:
                docs = index.search(search_query(question, pairs), k=settings.top_k, sources=sources)
            except Exception as e:
                st.error(f"Search failed. Is Ollama running with `{index.embed_model}`? ({e})")
                st.stop()
            if not docs:
                answer = "I couldn't find anything relevant in the selected files."
                st.markdown(answer)
            elif search_only:
                answer = "Here are the most relevant passages:\n\n" + "\n".join(
                    f"- **[{i}] {d.metadata['label']}**" for i, d in enumerate(docs, start=1)
                )
                st.markdown(answer)
            else:
                try:
                    answer = st.write_stream(stream_answer(make_llm(settings), question, docs, pairs))
                except Exception as e:
                    answer = f"⚠️ The model couldn't answer ({e}). The matching passages are below."
                    st.markdown(answer)
            show_sources(docs)
        history.append({"q": question, "a": answer, "docs": docs})
    if history and st.button("Clear chat"):
        history.clear()
        st.rerun()

# ---- Notes ----
elif mode == "📝 Notes":
    st.markdown("Revision notes with key ideas, terms, formulas and likely exam questions.")
    with st.form(f"notes-{course}"):
        topic = st.text_input("Topic (leave empty to cover the selected files)", placeholder="e.g. cell respiration")
        go = st.form_submit_button("Make notes", type="primary")
    if go:
        docs = gather(topic, max(settings.top_k, 10))
        try:
            notes = st.write_stream(stream_summary(make_llm(settings), topic, docs))
            st.session_state[f"notes-out-{course}"] = (notes, docs, topic)
        except Exception as e:
            llm_error(e)
    elif f"notes-out-{course}" in st.session_state:
        notes, docs, topic = st.session_state[f"notes-out-{course}"]
        st.markdown(notes)
    if f"notes-out-{course}" in st.session_state:
        notes, docs, topic = st.session_state[f"notes-out-{course}"]
        show_sources(docs)
        st.download_button("⬇️ Download notes (.md)", notes, file_name=f"{course} notes.md")

# ---- Quiz ----
elif mode == "🧠 Quiz me":
    qkey = f"quiz-{course}"
    with st.form(f"quizform-{course}"):
        c1, c2 = st.columns([3, 1])
        topic = c1.text_input("Topic (leave empty for a mix from the selected files)", placeholder="e.g. elasticity")
        n = c2.number_input("Questions", 3, 15, 5)
        go = st.form_submit_button("New quiz", type="primary")
    if go:
        docs = gather(topic, max(settings.top_k, 8))
        with st.spinner("🐸 Writing your quiz…"):
            try:
                quiz = make_quiz(make_llm(settings, json_mode=True, temperature=0.4), topic, docs, int(n))
            except Exception as e:
                llm_error(e)
                quiz = []
        if go and not quiz:
            st.warning("The model didn't produce usable questions. Try again, a narrower topic, or a bigger model.")
        st.session_state[qkey] = {"qs": quiz, "picked": {}, "checked": False}

    state = st.session_state.get(qkey)
    if state and state["qs"]:
        for i, q in enumerate(state["qs"]):
            st.markdown(f"**{i + 1}. {q.question}**")
            pick = st.radio(
                f"q{i}", q.options, index=None, key=f"{qkey}-{i}", label_visibility="collapsed",
                disabled=state["checked"],
            )
            state["picked"][i] = pick
            if state["checked"]:
                right = q.options[q.answer]
                if pick == right:
                    st.success(f"✅ Correct. {q.explanation}")
                else:
                    st.error(f"❌ Answer: **{right}**. {q.explanation}")
                if q.source:
                    st.markdown(f"<span class='cr-src'>📍 {q.source}</span>", unsafe_allow_html=True)
        if not state["checked"]:
            if st.button("Check answers", type="primary"):
                state["checked"] = True
                st.rerun()
        else:
            score = sum(state["picked"].get(i) == q.options[q.answer] for i, q in enumerate(state["qs"]))
            total = len(state["qs"])
            msg = "Ribbiting! 🐸🎉" if score == total else "Keep hopping, you've got this 🐸" if score < total / 2 else "Nice work 🐸"
            st.subheader(f"Score: {score}/{total}. {msg}")

# ---- Flashcards ----
else:
    fkey = f"cards-{course}"
    with st.form(f"cardform-{course}"):
        c1, c2 = st.columns([3, 1])
        topic = c1.text_input("Topic (leave empty for the selected files)", placeholder="e.g. Krebs cycle")
        n = c2.number_input("Cards", 5, 30, 10)
        go = st.form_submit_button("Make flashcards", type="primary")
    if go:
        docs = gather(topic, max(settings.top_k, 10))
        with st.spinner("🐸 Making flashcards…"):
            try:
                cards = make_cards(make_llm(settings, json_mode=True, temperature=0.3), topic, docs, int(n))
            except Exception as e:
                llm_error(e)
                cards = []
        if not cards:
            st.warning("The model didn't produce usable cards. Try again or pick a bigger model.")
        st.session_state[fkey] = cards

    cards = st.session_state.get(fkey) or []
    if cards:
        st.caption("Click a card to flip it.")
        cols = st.columns(2)
        for i, c in enumerate(cards):
            with cols[i % 2].expander(f"**{c.front}**"):
                st.markdown(c.back)
                if c.source:
                    st.markdown(f"<span class='cr-src'>📍 {c.source}</span>", unsafe_allow_html=True)
        st.download_button(
            "⬇️ Export for Anki / Quizlet (.csv)", cards_to_csv(cards), file_name=f"{course} flashcards.csv"
        )
