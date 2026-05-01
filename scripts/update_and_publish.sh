#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_DIR="${ROOT_DIR}/.run-lock"
LOG_PREFIX="[avanza-tracker]"

log() {
  printf '%s %s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "${LOG_PREFIX}" "$*"
}

cleanup() {
  rmdir "${LOCK_DIR}" 2>/dev/null || true
}

trap cleanup EXIT

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  log "Another update is already running; exiting."
  exit 0
fi

cd "${ROOT_DIR}"

if [[ ! -d .venv ]]; then
  log "Missing virtualenv at ${ROOT_DIR}/.venv"
  exit 1
fi

if [[ ! -f .env ]]; then
  log "Missing .env at ${ROOT_DIR}/.env"
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no -- site/portfolio.json)" ]]; then
  log "site/portfolio.json has uncommitted changes; refusing to overwrite."
  exit 1
fi

source .venv/bin/activate

log "Exporting latest portfolio snapshot."
python3 scripts/export_portfolio.py

if git diff --quiet -- site/portfolio.json; then
  log "No portfolio changes detected; nothing to publish."
  exit 0
fi

log "Publishing updated portfolio snapshot."
git add site/portfolio.json
git commit -m "Update portfolio snapshot"
git push origin HEAD

log "Publish completed."
