"""Streamlit UI. Run with:  crammphibian   (or: streamlit run crammphibian/app.py)"""

from __future__ import annotations

import html
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path

import streamlit as st

from crammphibian import companion as frog
from crammphibian.config import Settings
from crammphibian.index import StudyIndex
from crammphibian.loaders import UnsupportedFile
from crammphibian.ollama_check import has_model, installed_models, pick_chat_models, pick_embed_model
from crammphibian.qa import make_llm, search_query, stream_answer
from crammphibian.study import cards_to_csv, make_cards, make_quiz, stream_summary

MASCOT = Path(__file__).with_name("assets") / "mascot.png"
AVATAR = str(MASCOT) if MASCOT.exists() else frog.icon()

st.set_page_config(page_title="Crammphibian", page_icon=AVATAR, layout="wide")
st.markdown(f"<style>{frog.theme_css()}</style>", unsafe_allow_html=True)
if MASCOT.exists():
    st.logo(str(MASCOT), size="large")

settings = Settings()

ASK, NOTES, QUIZ, CARDS = "💬 Ask", "📝 Notes", "🧠 Quiz me", "🃏 Flashcards"
TIPS = {
    None: [
        "Name a course in the sidebar, then drop in your lecture PDFs and slides.",
        "One course per subject keeps answers focused. BIO 101 and ECON 200 stay separate.",
        "Everything runs on your computer. Your notes never leave it.",
        "Drag me anywhere you like. Double-click me to send me home.",
        "Need quiet? Click me, then Nap. I'll be on my lily pad.",
    ],
    ASK: [
        "Open Sources under an answer to see the exact page or slide it came from.",
        "Ask follow-ups like “why?” or “give an example”. I remember the last few turns.",
        "Use Files to use to focus on one lecture at a time.",
        "Search only mode skips the AI and jumps straight to the right slide.",
    ],
    NOTES: [
        "Leave the topic empty to get notes on the whole lecture.",
        "Download your notes as Markdown and paste them into your notes app.",
    ],
    QUIZ: [
        "Quiz me works best on one lecture at a time. Pick it in Files to use.",
        "Got one wrong? The 📍 line tells you which page to reread.",
        "Five questions a day beats fifty the night before. Ribbit.",
    ],
    CARDS: [
        "Click a card to flip it.",
        "Export to Anki or Quizlet with the CSV button.",
    ],
}


def tips_for(mode: str | None) -> list[str]:
    return TIPS.get(mode, []) + TIPS[None]


def sprite_img(name: str = "idle", cls: str = "") -> str:
    p = frog.frame_path(name)
    return f'<img class="cr-sprite {cls}" src="{frog.data_uri(p)}" alt="">' if p else "🐸"


def collections() -> list[str]:
    if not settings.data_dir.exists():
        return []
    return sorted(p.name for p in settings.data_dir.iterdir() if (p / "manifest.json").exists())


@st.cache_resource(show_spinner=False)
def get_index(name: str, embed_model: str) -> StudyIndex:
    return StudyIndex(name, replace(settings, embed_model=embed_model))


def plural(n: int, kind: str) -> str:
    unit = "page" if kind == "page" else "slide"
    return f"{n} {unit}{'' if n == 1 else 's'}"


# ---------------- sidebar: course, model, files ----------------
models = installed_models(settings.ollama_url)

with st.sidebar:
    st.markdown(
        f'<div class="cr-brand">{sprite_img()}<div><div class="cr-brand-name">Crammphibian</div>'
        '<div class="cr-brand-tag">your offline study buddy</div></div></div>',
        unsafe_allow_html=True,
    )

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

if models is None:
    frog.say("I can't hear Ollama croaking. Open the Ollama app, then refresh this page.", "sad", key="no-ollama")

if not course:
    frog.mount(tips_for(None))
    frog.say(
        "Hi, I'm Crammy! Name a course in the sidebar and feed me your slides. I'll help you cram.",
        "happy", key="hello",
    )
    st.markdown(
        f"""<div class="cr-hero">
  <div class="cr-hero-frog">{sprite_img("happy", "cr-bounce")}</div>
  <h1>Crammphibian</h1>
  <p>Load your lecture PDFs and PowerPoints, then ask questions, get revision notes, quiz yourself
  and make flashcards. Every answer is cited to the exact page or slide, and it all runs on your computer.</p>
</div>
<div class="cr-steps">
  <div class="cr-step"><b>1</b><span>Name a course in the sidebar, like <i>BIO 101</i></span></div>
  <div class="cr-step"><b>2</b><span>Drop in your PDFs and <code>.pptx</code> slides</span></div>
  <div class="cr-step"><b>3</b><span>Ask, make notes, quiz yourself, flip flashcards</span></div>
</div>""",
        unsafe_allow_html=True,
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
                frog.say(f"I'm missing the {m} model. The sidebar shows the one-line fix.", "sad", key=f"missing-{m}")

    st.divider()
    st.subheader("📚 Files")
    uploads = st.file_uploader(
        "Add PDFs or PowerPoints", type=["pdf", "pptx"], accept_multiple_files=True, key=f"up-{course}"
    )
    if uploads and st.button("Add to course", type="primary", use_container_width=True):
        progress = st.progress(0.0)
        added = 0
        for n, up in enumerate(uploads, start=1):
            progress.progress((n - 1) / len(uploads), text=f"Reading {up.name}…")
            with tempfile.NamedTemporaryFile(suffix=Path(up.name).suffix, delete=False) as tmp:
                tmp.write(up.getbuffer())
            try:
                rep = index.add_file(tmp.name, display_name=up.name)
                if rep["status"] == "indexed":
                    added += rep["units"]
                    st.success(f"{up.name}: {plural(rep['units'], rep['kind'])}")
                else:
                    st.info(f"{up.name}: {rep['reason']}")
            except UnsupportedFile as e:
                st.error(str(e))
            except Exception as e:  # most often: Ollama not running / model missing
                st.error(f"{up.name}: {e}")
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        progress.empty()
        if added:
            frog.say(f"Yum, fresh notes! I just read {added} pages and slides. Ask me anything.", "happy",
                     key=uuid.uuid4().hex)
        else:
            frog.say("Hmm, I couldn't read anything new from those files.", "sad", key=uuid.uuid4().hex)

    if index.files:
        st.markdown(
            "".join(
                f'<div class="cr-file"><span>📄 {html.escape(f)}</span><small>{plural(i["units"], i["kind"])}</small></div>'
                for f, i in index.files.items()
            ),
            unsafe_allow_html=True,
        )
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
n_units = sum(i["units"] for i in index.files.values())
st.markdown(
    f'<div class="cr-course"><h2>{html.escape(course)}</h2>'
    f'<span class="cr-chip">{len(index.files)} file{"" if len(index.files) == 1 else "s"} · '
    f'{n_units} pages &amp; slides</span></div>',
    unsafe_allow_html=True,
)
if index.is_empty():
    frog.mount(tips_for(None))
    frog.say(f"{course} looks empty. Feed me some PDFs or slides from the sidebar!", "talk", key=f"empty-{course}")
    st.markdown(
        f'<div class="cr-empty">{sprite_img("think")}<div><b>No files yet.</b><br>'
        "Add your lecture PDFs or PowerPoints in the sidebar, then come back here.</div></div>",
        unsafe_allow_html=True,
    )
    st.stop()

mode = st.segmented_control(
    "Mode", [ASK, NOTES, QUIZ, CARDS], default=ASK, key=f"mode-{course}", label_visibility="collapsed",
) or ASK
frog.mount(tips_for(mode))
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
    st.error(f"The model couldn't finish ({e}). Check that Ollama is running, or try another model.")
    frog.say("Oof, the model tripped over its own feet. Is Ollama running?", "sad", key=uuid.uuid4().hex)


SUGGESTIONS = ["Summarise the key ideas", "What is likely to be on the exam?", "Explain the hardest concept simply"]

# ---- Ask ----
if mode == ASK:
    search_only = st.toggle("Search only (just show the best passages, no AI answer)", value=False)
    history: list[dict] = st.session_state.setdefault(f"chat-{course}", [])
    picked = None
    if not history:
        st.markdown('<div class="cr-hint">Try one of these, or type your own question below.</div>',
                    unsafe_allow_html=True)
        cols = st.columns(len(SUGGESTIONS))
        for c, s in zip(cols, SUGGESTIONS):
            if c.button(s, use_container_width=True, key=f"sugg-{s}"):
                picked = s
    for turn in history:
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(turn["q"])
        with st.chat_message("assistant", avatar=AVATAR):
            st.markdown(turn["a"])
            show_sources(turn["docs"])

    question = st.chat_input("Ask about your notes, e.g. “Explain the Krebs cycle step by step”") or picked
    if question:
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(question)
        pairs = [(t["q"], t["a"]) for t in history]
        with st.chat_message("assistant", avatar=AVATAR):
            try:
                docs = index.search(search_query(question, pairs), k=settings.top_k, sources=sources)
            except Exception as e:
                st.error(f"Search failed. Is Ollama running with `{index.embed_model}`? ({e})")
                frog.say("I couldn't search your notes. Is Ollama running?", "sad", key=uuid.uuid4().hex)
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
        if picked:
            st.rerun()
    if history and st.button("Clear chat"):
        history.clear()
        st.rerun()

# ---- Notes ----
elif mode == NOTES:
    st.markdown('<div class="cr-hint">Revision notes with key ideas, terms, formulas and likely exam questions.</div>',
                unsafe_allow_html=True)
    with st.form(f"notes-{course}"):
        topic = st.text_input("Topic (leave empty to cover the selected files)", placeholder="e.g. cell respiration")
        go = st.form_submit_button("Make notes", type="primary")
    if go:
        docs = gather(topic, max(settings.top_k, 10))
        try:
            notes = st.write_stream(stream_summary(make_llm(settings), topic, docs))
            st.session_state[f"notes-out-{course}"] = (notes, docs, topic)
            frog.say("Notes are ready! Grab them with the download button.", "happy", key=uuid.uuid4().hex)
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
elif mode == QUIZ:
    qkey = f"quiz-{course}"
    with st.form(f"quizform-{course}"):
        c1, c2 = st.columns([3, 1])
        topic = c1.text_input("Topic (leave empty for a mix from the selected files)", placeholder="e.g. elasticity")
        n = c2.number_input("Questions", 3, 15, 5)
        go = st.form_submit_button("New quiz", type="primary")
    if go:
        docs = gather(topic, max(settings.top_k, 8))
        with st.spinner("Writing your quiz…"):
            try:
                quiz = make_quiz(make_llm(settings, json_mode=True, temperature=0.4), topic, docs, int(n))
            except Exception as e:
                llm_error(e)
                quiz = []
        if not quiz:
            st.warning("The model didn't produce usable questions. Try again, a narrower topic, or a bigger model.")
        else:
            frog.say(f"{len(quiz)} questions, fresh from the pond. Good luck!", "happy", key=uuid.uuid4().hex)
        st.session_state[qkey] = {"qs": quiz, "picked": {}, "checked": False, "id": uuid.uuid4().hex}

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
                    st.markdown(f"<span class='cr-src'>📍 {html.escape(q.source)}</span>", unsafe_allow_html=True)
        if not state["checked"]:
            if st.button("Check answers", type="primary"):
                state["checked"] = True
                st.rerun()
        else:
            score = sum(state["picked"].get(i) == q.options[q.answer] for i, q in enumerate(state["qs"]))
            total = len(state["qs"])
            if score == total:
                msg, face, line = "Ribbiting! A perfect score.", "happy", "PERFECT! Ribbit ribbit! 🎉"
            elif score >= total / 2:
                msg, face, line = "Nice work. Reread the 📍 pages for the ones you missed.", "happy", "Nice work!"
            else:
                msg, face, line = "Keep hopping, you've got this. The 📍 lines show where to look.", "sad", "Keep hopping!"
            st.markdown(
                f'<div class="cr-score">{sprite_img(face)}<div><div class="cr-score-num">{score}/{total}</div>'
                f"<div>{html.escape(msg)}</div></div></div>",
                unsafe_allow_html=True,
            )
            frog.say(f"{score} out of {total}. {line}", face, key=f"score-{state.get('id')}")

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
        with st.spinner("Making flashcards…"):
            try:
                cards = make_cards(make_llm(settings, json_mode=True, temperature=0.3), topic, docs, int(n))
            except Exception as e:
                llm_error(e)
                cards = []
        if not cards:
            st.warning("The model didn't produce usable cards. Try again or pick a bigger model.")
        else:
            frog.say(f"{len(cards)} flashcards ready. Click one to flip it!", "happy", key=uuid.uuid4().hex)
        st.session_state[fkey] = cards

    cards = st.session_state.get(fkey) or []
    if cards:
        st.markdown('<div class="cr-hint">Click a card to flip it.</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="cr-cards">'
            + "".join(
                f'<label class="cr-flip"><input type="checkbox"><div class="cr-flip-inner">'
                f'<div class="cr-face cr-front"><small>Q{i + 1}</small><p>{html.escape(c.front)}</p></div>'
                f'<div class="cr-face cr-back"><p>{html.escape(c.back)}</p>'
                + (f'<small>📍 {html.escape(c.source)}</small>' if c.source else "")
                + "</div></div></label>"
                for i, c in enumerate(cards)
            )
            + "</div>",
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇️ Export for Anki / Quizlet (.csv)", cards_to_csv(cards), file_name=f"{course} flashcards.csv"
        )
