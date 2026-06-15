#!/usr/bin/env bash
# Build and start API + MongoDB on the server.
# Run from anywhere: sudo bash deploy/start.sh

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

set -a
# shellcheck disable=SC1091
# Strip Windows CRLF if .env was uploaded from Windows
source <(sed 's/\r$//' .env)
set +a

if [[ -z "${MONGO_ROOT_USERNAME:-}" || -z "${MONGO_ROOT_PASSWORD:-}" ]]; then
  echo "Missing MONGO_ROOT_USERNAME or MONGO_ROOT_PASSWORD in .env"
  exit 1
fi

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

"${DOCKER[@]}" compose \
  --project-directory "$ROOT_DIR" \
  --env-file "$ROOT_DIR/.env" \
  -f deploy/docker-compose.prod.yml \
  up -d --build

echo ""
echo "Repo: $ROOT_DIR"
echo "API listening on http://127.0.0.1:8002 (localhost only)."
echo "Test: curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/docs"
echo "Public URL after nginx: https://focms.megaannum.ai:8001/docs"
