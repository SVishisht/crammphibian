#!/usr/bin/env bash
# Crammphibian installer for macOS / Linux.
#   ./install.sh          standard models (~2.3 GB download, needs ~4 GB free RAM)
#   ./install.sh --lite   smallest models (~450 MB download, runs in under 1 GB RAM)
set -euo pipefail
cd "$(dirname "$0")"

LITE=0
[ "${1:-}" = "--lite" ] && LITE=1
if [ $LITE = 1 ]; then
  EMBED_MODEL="${CRAMMPHIBIAN_EMBED_MODEL:-all-minilm}"
  LLM_MODEL="${CRAMMPHIBIAN_LLM_MODEL:-qwen2.5:0.5b}"
  SIZE="~450 MB"
else
  EMBED_MODEL="${CRAMMPHIBIAN_EMBED_MODEL:-nomic-embed-text}"
  LLM_MODEL="${CRAMMPHIBIAN_LLM_MODEL:-llama3.2:3b}"
  SIZE="~2.3 GB"
fi

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
echo "→ Installing Crammphibian (a minute or two the first time)"
.venv/bin/python -m pip install --quiet -e .

if command -v ollama >/dev/null 2>&1; then
  echo "→ Downloading local AI models with Ollama (one time, $SIZE)"
  ollama pull "$EMBED_MODEL"
  ollama pull "$LLM_MODEL"
else
  echo
  echo "⚠️  Ollama isn't installed. It runs the AI models on your computer."
  echo "   1. Install it from https://ollama.com/download"
  echo "   2. Then run:  ollama pull $EMBED_MODEL && ollama pull $LLM_MODEL"
fi

cat > start.sh <<EOF
#!/usr/bin/env bash
export CRAMMPHIBIAN_EMBED_MODEL="\${CRAMMPHIBIAN_EMBED_MODEL:-$EMBED_MODEL}"
export CRAMMPHIBIAN_LLM_MODEL="\${CRAMMPHIBIAN_LLM_MODEL:-$LLM_MODEL}"
cd "\$(dirname "\$0")" && exec .venv/bin/crammphibian "\$@"
EOF
chmod +x start.sh

echo
echo "✅ Done. Start it any time with:  ./start.sh"
