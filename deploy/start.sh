#!/usr/bin/env bash
# Build and start API + MongoDB on the server.
# Run from repo root: bash deploy/start.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env in repo root. Copy deploy/.env.production.example to .env and edit it."
  exit 1
fi

if [[ ! -f firebase-service-account.json ]]; then
  echo "Missing firebase-service-account.json in repo root."
  exit 1
fi

docker compose -f deploy/docker-compose.prod.yml up -d --build

echo ""
echo "API listening on http://127.0.0.1:8002 (localhost only)."
echo "Test: curl -s http://127.0.0.1:8002/docs | head"
echo "Public URL after nginx: https://focms.megaannum.ai:8001/docs"
