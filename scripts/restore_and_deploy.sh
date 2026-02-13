#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER no está definido (revisá .env)}"
: "${POSTGRES_DB:?POSTGRES_DB no está definido (revisá .env)}"

DUMP_FILE="${1:-}"
if [[ -z "$DUMP_FILE" ]]; then
  echo "Uso: $0 <ruta_dump> [ref_git]" >&2
  exit 1
fi
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Error: dump no encontrado: $DUMP_FILE" >&2
  exit 1
fi

GIT_REF="${2:-main}"

echo "[deploy] Actualizando código a $GIT_REF"
git fetch --all --tags
git checkout "$GIT_REF"
if [[ "$GIT_REF" == "main" ]]; then
  git pull --ff-only origin main
fi

echo "[deploy] Levantando base de datos"
docker compose up -d db

echo "[deploy] Restaurando dump: $DUMP_FILE"
cat "$DUMP_FILE" | docker compose exec -T db pg_restore \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner

echo "[deploy] Levantando app"
docker compose up -d app

echo "[deploy] Smoke test en /health"
curl -fsS http://localhost:8000/health >/dev/null

echo "[deploy] OK: restauración + deploy completados"
