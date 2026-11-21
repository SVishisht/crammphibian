"""Command line entry points.

  crammphibian                      open the app in your browser
  crammphibian index COURSE FILES…  index files without the UI
  crammphibian ask COURSE "question"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _run_ui() -> None:
    from streamlit.web import cli as stcli

    app = Path(__file__).with_name("app.py")
    sys.argv = ["streamlit", "run", str(app), "--browser.gatherUsageStats=false",
        "--server.address=localhost",
        "--client.toolbarMode=minimal",
    ]
    sys.exit(stcli.main())


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("ui", "app"):
        _run_ui()

    p = argparse.ArgumentParser(prog="crammphibian")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index", help="add files to a course")
    pi.add_argument("course")
    pi.add_argument("files", nargs="+")
    pa = sub.add_parser("ask", help="ask a question")
    pa.add_argument("course")
    pa.add_argument("question")
    pa.add_argument("--search-only", action="store_true", help="show passages, skip the AI answer")
    args = p.parse_args(argv)

    from .config import Settings
    from .index import StudyIndex

    settings = Settings()
    index = StudyIndex(args.course, settings)

    if args.cmd == "index":
        for f in args.files:
            try:
                print(index.add_file(f))
            except Exception as e:
                print(f"{f}: {e}", file=sys.stderr)
        return

    docs = index.search(args.question)
    if not docs:
        print("Nothing found. Did you index files into this course?")
        return
    if not args.search_only:
        from .qa import make_llm, stream_answer

        for piece in stream_answer(make_llm(settings), args.question, docs):
            print(piece, end="", flush=True)
        print("\n")
    print("Sources:")
    for i, d in enumerate(docs, start=1):
        print(f"  [{i}] {d.metadata['label']}")


if __name__ == "__main__":
    main()
