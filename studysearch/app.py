"""Streamlit UI. Run with:  study-search   (or: streamlit run studysearch/app.py)"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from studysearch.config import Settings
from studysearch.index import StudyIndex
from studysearch.loaders import UnsupportedFile
from studysearch.ollama_check import has_model, installed_models
from studysearch.qa import make_llm, search_query, stream_answer

st.set_page_config(page_title="Study Search", page_icon="📚", layout="wide")
settings = Settings()


def collections() -> list[str]:
    if not settings.data_dir.exists():
        return []
    return sorted(p.name for p in settings.data_dir.iterdir() if (p / "manifest.json").exists())


@st.cache_resource(show_spinner=False)
def get_index(name: str) -> StudyIndex:
    return StudyIndex(name, settings)


# ---------------- sidebar: courses, files, model ----------------
with st.sidebar:
    st.title("📚 Study Search")

    existing = collections()
    options = existing + ["➕ New course…"]
    choice = st.selectbox("Course", options, index=0)
    if choice == "➕ New course…" or not existing:
        new_name = st.text_input("Course name", placeholder="e.g. BIO 101")
        course = new_name.strip()
    else:
        course = choice

    st.divider()
    st.subheader("Model")
    models = installed_models(settings.ollama_url)
    use_cloud = st.toggle(
        "Use cloud model (OpenAI API key)",
        value=settings.llm_provider == "openai",
        help="Off = fully offline with Ollama. Embeddings and your files always stay local; "
        "with this on, the question and the matching excerpts are sent to the API.",
    )
    settings.llm_provider = "openai" if use_cloud else "ollama"
    if use_cloud:
        settings.openai_model = st.text_input("Cloud model", settings.openai_model)
    else:
        chat_models = [m for m in (models or []) if "embed" not in m] or [settings.llm_model]
        default = chat_models.index(settings.llm_model) if settings.llm_model in chat_models else 0
        settings.llm_model = st.selectbox("Local model", chat_models, index=default)

    # Health checks, in plain words.
    if models is None:
        st.error("Ollama isn't running. Start the Ollama app, then refresh this page.")
    else:
        for needed in [settings.embed_model] + ([] if use_cloud else [settings.llm_model]):
            if not has_model(models, needed):
                st.warning(f"Model `{needed}` isn't downloaded. Run:\n\n`ollama pull {needed}`")

    settings.top_k = st.slider("Passages per answer", 3, 12, settings.top_k)

if not course:
    st.info("👈 Name your course in the sidebar to get started (e.g. *BIO 101*).")
    st.stop()

index = get_index(course)

with st.sidebar:
    st.divider()
    st.subheader("Files")
    uploads = st.file_uploader(
        "Add PDFs or PowerPoints", type=["pdf", "pptx"], accept_multiple_files=True, key=f"up-{course}"
    )
    if uploads and st.button("Index files", type="primary", use_container_width=True):
        progress = st.progress(0.0)
        for n, up in enumerate(uploads, start=1):
            progress.progress((n - 1) / len(uploads), text=f"Reading {up.name}…")
            with tempfile.NamedTemporaryFile(suffix=Path(up.name).suffix, delete=False) as tmp:
                tmp.write(up.getbuffer())
            try:
                rep = index.add_file(tmp.name, display_name=up.name)
                if rep["status"] == "indexed":
                    unit = "pages" if rep["kind"] == "page" else "slides"
                    st.success(f"{up.name}: {rep['units']} {unit}")
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
        with st.expander("Remove files"):
            to_remove = st.selectbox("File", list(index.files), key=f"rmsel-{course}")
            if st.button("Remove this file", use_container_width=True):
                index.remove_file(to_remove)
                st.rerun()
            st.divider()
            if st.button(f"Delete course “{course}”"):
                index.delete()
                get_index.clear()
                st.session_state.pop(f"chat-{course}", None)
                st.rerun()

# ---------------- main: chat ----------------
st.header(course)
if index.is_empty():
    st.info("Add your lecture PDFs and slides in the sidebar, then ask anything about them.")
    st.stop()

only = st.multiselect("Search only in (optional)", list(index.files), placeholder="All files")
search_only = st.toggle("Search only (no AI answer, just the best passages)", value=False)

chat_key = f"chat-{course}"
history: list[dict] = st.session_state.setdefault(chat_key, [])


def show_sources(docs):
    with st.expander(f"Sources ({len(docs)})"):
        for i, d in enumerate(docs, start=1):
            st.markdown(f"**[{i}] {d.metadata['label']}**")
            text = d.page_content
            st.caption(text[:700] + ("…" if len(text) > 700 else ""))


for turn in history:
    with st.chat_message("user"):
        st.markdown(turn["q"])
    with st.chat_message("assistant"):
        st.markdown(turn["a"])
        show_sources(turn["docs"])

question = st.chat_input("Ask about your notes, e.g. “Explain the Krebs cycle step by step”")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    pairs = [(t["q"], t["a"]) for t in history]
    with st.chat_message("assistant"):
        try:
            docs = index.search(search_query(question, pairs), k=settings.top_k, sources=only or None)
        except Exception as e:
            st.error(f"Search failed. Is Ollama running with `{settings.embed_model}`? ({e})")
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
