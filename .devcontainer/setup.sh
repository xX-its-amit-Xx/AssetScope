#!/usr/bin/env bash
# Codespaces postCreate: make the box ready to run AssetScope fully locally.
# - zstd is required by the current Ollama installer.
# - install the Ollama binary (does NOT pull a model — do that on demand).
# - install the Python project (so pytest / assetscope-mcp / the API work).
set -e
sudo apt-get update -qq && sudo apt-get install -y -qq zstd
curl -fsSL https://ollama.com/install.sh | sh || echo "WARN: Ollama install failed; you can still run with ASSETSCOPE_LLM_BACKEND=anthropic"
pip install -e ".[dev]" || echo "WARN: pip install failed; run it manually"

cat <<'MSG'

AssetScope Codespace ready. To run the full stack with a local model:

  # 1) start a local model server + pull a small tool-capable model
  OLLAMA_HOST=0.0.0.0:11434 nohup ollama serve >/tmp/ollama.log 2>&1 &
  ollama pull qwen2.5:3b

  # 2) point AssetScope at it (one line, copy-paste safe), then bring up the stack
  printf 'ASSETSCOPE_LLM_BACKEND=local\nASSETSCOPE_LLM_BASE_URL=http://host.docker.internal:11434/v1\nASSETSCOPE_LLM_MODEL=qwen2.5:3b\nASSETSCOPE_USE_FAKE_EMBEDDINGS=1\n' > .env
  docker compose up -d --build

  # 3) open the forwarded port 8080 for the UI, or query the API:
  curl -s -X POST localhost:8000/query -H 'Content-Type: application/json' \
    -d '{"query":"competitive landscape for KRAS G12C inhibitors in NSCLC"}'
MSG
