# 📚 Study Search

Ask questions across all your lecture PDFs and PowerPoint slides, and get answers
**with page and slide citations**, running entirely on your own computer.

> "Explain the Krebs cycle step by step" → an answer built only from your notes,
> citing *Biology Lecture 3.pdf, p. 2* and *Week 4 slides.pptx, slide 7*.

- **Private and offline.** Your files never leave your laptop. No account, no API key.
- **PDFs and PowerPoints (.pptx)**, including tables and speaker notes.
- **Semantic + keyword search.** Finds passages by meaning *and* by exact terms
  (formula names, acronyms).
- **One course per subject.** Keep BIO 101 and ECON 200 separate; indexes are
  saved, so you only add files once.
- **Search-only mode** to jump straight to the right slide without an AI answer.

## Install (about 5 minutes, once)

You need **Python 3.10+** ([download](https://www.python.org/downloads/)) and
**Ollama**, the free app that runs AI models locally ([download](https://ollama.com/download)).
Install both, then download this folder and run:

**macOS / Linux**
```bash
./install.sh
```

**Windows** (PowerShell, inside the folder)
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer creates a private Python environment in `.venv` and downloads two
models (~2.3 GB total, one time): `nomic-embed-text` for search and `llama3.2:3b`
for answers.

## Use

Start it with `./start.sh` (macOS/Linux) or double-click `start.bat` (Windows).
Your browser opens at http://localhost:8501.

1. Type a course name in the sidebar (e.g. *BIO 101*).
2. Drop in your PDFs and `.pptx` files and click **Index files**.
3. Ask questions. Open **Sources** under each answer to see the exact passages.

There's also a command line:

```bash
.venv/bin/study-search index "BIO 101" lecture1.pdf lecture2.pptx
.venv/bin/study-search ask "BIO 101" "What is oxidative phosphorylation?"
```

## Settings

All optional, set as environment variables before starting:

| Variable | Default | What it does |
|---|---|---|
| `STUDYSEARCH_LLM_MODEL` | `llama3.2:3b` | Any Ollama chat model. Use `llama3.1:8b` or `qwen2.5:7b` for better answers if you have 16 GB RAM. You can also switch in the sidebar. |
| `STUDYSEARCH_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model. Changing it means re-adding your files. |
| `STUDYSEARCH_HOME` | `~/.studysearch` | Where course indexes are saved. |
| `OLLAMA_HOST` | `http://localhost:11434` | Where Ollama is running. |

**Optional cloud model.** If your laptop is slow, you can have answers written by
an OpenAI model instead: `.venv/bin/pip install -e ".[cloud]"`, set `OPENAI_API_KEY`,
then turn on **Use cloud model** in the sidebar. Search still runs locally, but your
question and the matching excerpts are sent to the API.

## Limitations (v0.1)

- Old `.ppt` files: save them as `.pptx` or PDF first.
- Scanned PDFs (images of pages) have no text to read; OCR isn't supported yet.
- Diagrams and images aren't understood, only the text on the page or slide.
- Small local models can be slow on older laptops (expect 5–30 s per answer)
  and are less precise than big cloud models. Always check the cited pages.

## How it works

```
PDF pages / slides ──► text per page/slide ──► ~1000-char chunks
                                                  │
                      ┌───────────────────────────┴──────────────┐
                 FAISS vectors (Ollama embeddings)        BM25 keyword index
                      └──────────── reciprocal rank fusion ──────┘
                                         │
                   top passages, numbered [1]..[n] with file + page/slide
                                         │
                 local LLM (Ollama) via LangChain ──► answer with [n] citations
```

Code: `studysearch/loaders.py` (PDF/PPTX parsing), `index.py` (hybrid search,
saved per course), `qa.py` (RAG prompt), `app.py` (Streamlit UI), `cli.py`.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests use stand-in embeddings and a fake chat model, so they run without Ollama.
