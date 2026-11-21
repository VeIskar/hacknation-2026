#!/usr/bin/env bash
# Pobiera model do wolumenu `ollama-models` (raz, ok. 3,4 GB dla qwen3.5:4b). Potem działa offline.
#   bash scripts/pull_model.sh            model z LLM_MODEL (powłoka, potem .env), inaczej qwen3.5:4b
#   bash scripts/pull_model.sh bielik...  inny model (SPEC „Model”: zmiana tylko LLM_MODEL)
set -euo pipefail
cd "$(dirname "$0")/.."

model="${1:-${LLM_MODEL:-}}"
if [ -z "$model" ] && [ -f .env ]; then
  model="$(sed -n 's/^LLM_MODEL=//p' .env | tail -n 1 | tr -d "\"' \r")"
fi
model="${model:-qwen3.5:4b}"

docker compose up -d --build ollama

echo "Czekam na serwer ollama..."
for _ in $(seq 1 60); do
  if docker compose exec -T ollama ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T ollama ollama list >/dev/null

echo "Pobieram model: $model"
docker compose exec -T ollama ollama pull "$model"
docker compose exec -T ollama ollama list
