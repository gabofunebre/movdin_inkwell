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

OUT_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${1:-$OUT_DIR/movdin_${STAMP}.dump}"

if [[ -f "$OUT_FILE" ]]; then
  echo "Error: el archivo de salida ya existe: $OUT_FILE" >&2
  exit 1
fi

echo "[backup] Deteniendo app para evitar escrituras durante el dump..."
docker compose stop app

restore_app() {
  echo "[backup] Reiniciando app..."
  docker compose start app >/dev/null 2>&1 || true
}
trap restore_app EXIT

echo "[backup] Generando dump en $OUT_FILE"
docker compose exec -T db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -Fc > "$OUT_FILE"

echo "[backup] Dump creado correctamente: $OUT_FILE"
