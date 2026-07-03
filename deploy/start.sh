#!/usr/bin/env bash
# Build and start API + MongoDB on the server.
# Run from anywhere: sudo bash deploy/start.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env in repo root. Copy deploy/.env.dev.example or deploy/.env.production.example to .env and edit it."
  exit 1
fi

set -a
# shellcheck disable=SC1091
# Strip Windows CRLF if .env was uploaded from Windows
source <(sed 's/\r$//' .env)
set +a

FIREBASE_CREDS="${FIREBASE_CREDENTIALS_PATH:-./firebase-service-account.json}"
if [[ -d "$FIREBASE_CREDS" ]]; then
  echo "ERROR: $FIREBASE_CREDS is a directory (Docker often creates this when the JSON was missing)."
  echo "  rm -rf '$FIREBASE_CREDS' then re-upload the file via scp."
  exit 1
fi
if [[ ! -f "$FIREBASE_CREDS" ]]; then
  echo "Missing Firebase service account at $FIREBASE_CREDS (FIREBASE_CREDENTIALS_PATH in .env)."
  exit 1
fi

if [[ -z "${MONGO_ROOT_USERNAME:-}" || -z "${MONGO_ROOT_PASSWORD:-}" ]]; then
  echo "Missing MONGO_ROOT_USERNAME or MONGO_ROOT_PASSWORD in .env"
  exit 1
fi

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi

# Docker Compose reads --env-file literally; strip CRLF from Windows uploads.
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
sed 's/\r$//' .env > "$ENV_FILE"

"${DOCKER[@]}" compose \
  --project-directory "$ROOT_DIR" \
  --env-file "$ENV_FILE" \
  -f deploy/docker-compose.prod.yml \
  up -d --build

echo ""
echo "Repo: $ROOT_DIR"
echo "API listening on http://127.0.0.1:8002 (localhost only)."
echo "Test: curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/docs"
echo "Public URL after nginx: https://focms.megaannum.ai:8001/docs"
