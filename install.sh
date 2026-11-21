#!/usr/bin/env bash
# Study Search installer for macOS / Linux.  Usage:  ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

EMBED_MODEL="${STUDYSEARCH_EMBED_MODEL:-nomic-embed-text}"
LLM_MODEL="${STUDYSEARCH_LLM_MODEL:-llama3.2:3b}"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Python 3.10+ is required. Get it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

echo "→ Creating a private Python environment in .venv (using $PY)"
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
echo "→ Installing Study Search (a minute or two the first time)"
.venv/bin/python -m pip install --quiet -e .

if command -v ollama >/dev/null 2>&1; then
  echo "→ Downloading local AI models with Ollama (one time, ~2.3 GB)"
  ollama pull "$EMBED_MODEL"
  ollama pull "$LLM_MODEL"
else
  echo
  echo "⚠️  Ollama isn't installed. It runs the AI models on your computer."
  echo "   1. Install it from https://ollama.com/download"
  echo "   2. Then run:  ollama pull $EMBED_MODEL && ollama pull $LLM_MODEL"
fi

cat > start.sh <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")" && exec .venv/bin/study-search "$@"
EOF
chmod +x start.sh

echo
echo "✅ Done. Start it any time with:  ./start.sh"
