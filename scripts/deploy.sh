#!/usr/bin/env bash
#
# deploy.sh — pull latest master and redeploy with minimum downtime.
#
# Run manually on the dev box in /srv/khab, after init-server.sh has been run
# once. This is the ONLY script needed for routine deploys.
#
# What it does:
#   1. git pull --ff-only origin master   (records old commit for rollback)
#   2. builds the new Docker image BEFORE touching running containers
#   3. up -d — recreates only changed containers; app re-runs migrate +
#      collectstatic on start
#   4. waits for app to be healthy; on failure prints the rollback command
#   5. graceful  nginx -t && systemctl reload nginx
#
# Usage:
#   ./scripts/deploy.sh [--no-nginx] [--branch <name>]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.prod.yaml"
BRANCH="master"
RELOAD_NGINX=1

while [ $# -gt 0 ]; do
  case "$1" in
    --no-nginx) RELOAD_NGINX=0; shift ;;
    --branch)   BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

log(){  printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok(){   printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){  printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

cd "$REPO_DIR"
[ -f .env ] || die ".env missing — run scripts/prepare-server.sh first."

# ── 1. Pull ──────────────────────────────────────────────────────────────────
OLD_COMMIT="$(git rev-parse HEAD)"
log "Pulling origin/$BRANCH (current: ${OLD_COMMIT:0:8})..."
git fetch --quiet origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
NEW_COMMIT="$(git rev-parse HEAD)"
if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
  ok "Already up to date — rebuilding anyway to pick up any local/env changes."
else
  ok "Updated ${OLD_COMMIT:0:8} → ${NEW_COMMIT:0:8}."
fi

# ── 2. Build the new image first (no downtime yet) ───────────────────────────
log "Building Docker image..."
docker compose -f "$COMPOSE_FILE" build
ok "Image built."

# ── 3. Recreate changed containers ───────────────────────────────────────────
log "Recreating containers (app re-runs migrate + collectstatic)..."
docker compose -f "$COMPOSE_FILE" up -d
ok "Stack updated."

# ── 4. Health gate + rollback hint ───────────────────────────────────────────
log "Waiting for app to become healthy..."
app_cid="$(docker compose -f "$COMPOSE_FILE" ps -q app)"
healthy=0
for i in $(seq 1 30); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$app_cid" 2>/dev/null || echo '')"
  if [ "$status" = "healthy" ]; then healthy=1; break; fi
  printf '  %2d/30 (%s)\n' "$i" "${status:-starting}"
  sleep 5
done
if [ "$healthy" -ne 1 ]; then
  warn "app did not become healthy. Recent logs:"
  docker compose -f "$COMPOSE_FILE" logs --tail 40 app || true
  die "Deploy unhealthy. Roll back with:
       git reset --hard $OLD_COMMIT && ./scripts/deploy.sh
     Note: a migration that already applied is NOT undone by that reset."
fi
ok "app is healthy."

# ── 5. Graceful nginx reload ─────────────────────────────────────────────────
if [ "$RELOAD_NGINX" -eq 1 ]; then
  log "Reloading nginx..."
  if sudo nginx -t; then
    sudo systemctl reload nginx
    ok "nginx reloaded."
  else
    warn "nginx -t failed — NOT reloading. Fix config, then: sudo systemctl reload nginx"
  fi
fi

log "Deploy complete (${NEW_COMMIT:0:8})."
