#!/usr/bin/env bash
#
# init-server.sh — one-time KHA Boutique production bring-up in /srv/khab.
#
#   - verifies prerequisites and .env
#   - brings up the Docker stack (app/db/backup) with --build
#   - waits for app to report healthy
#   - makes the stack survive reboots (docker enabled at boot + khab.service)
#   - optionally installs the host nginx site (--with-nginx)
#   - optionally creates a Django superuser
#
# Safe to re-run: every step is idempotent.
#
# Usage:
#   ./scripts/init-server.sh [--with-nginx]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.prod.yaml"
WITH_NGINX=0

for arg in "$@"; do
  case "$arg" in
    --with-nginx) WITH_NGINX=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

log(){  printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok(){   printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){  printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

cd "$REPO_DIR"

# ── 1. Prerequisites ─────────────────────────────────────────────────────────
log "Checking prerequisites..."
for bin in docker git; do
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' is not installed or not on PATH."
done
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) is not available."
[ "$WITH_NGINX" -eq 1 ] && { command -v nginx >/dev/null 2>&1 || die "nginx not found but --with-nginx given."; }
ok "docker and git present."

# ── 2. .env ──────────────────────────────────────────────────────────────────
[ -f .env ] || die ".env missing — run scripts/prepare-server.sh first."
grep -q '^DEBUG=True' .env && warn "DEBUG=True in .env — this should be False in production."
# Last line of defence: prepare-server.sh should have replaced these, but a
# placeholder reaching production means public-repo values are securing real
# sessions and a real database.
for key in SECRET_KEY POSTGRES_PASSWORD; do
  value="$(sed -n "s/^$key=//p" .env | head -1)"
  case "${value:-}" in
    ''|*generate-me*|*your*|*YOUR*|*change*|*CHANGE*|*example*|*insecure*|khab)
      die "$key is still a placeholder ('${value:-empty}') — re-run scripts/prepare-server.sh." ;;
  esac
done
SECRET_LEN="$(sed -n 's/^SECRET_KEY=//p' .env | head -1 | wc -c)"
[ "$SECRET_LEN" -ge 50 ] || die "SECRET_KEY is only $((SECRET_LEN-1)) characters — re-run scripts/prepare-server.sh."

# First ALLOWED_HOSTS entry: the address the healthcheck sends as its Host
# header, and the one to verify against. No hostname exists — this is an IP.
PRIMARY_HOST="$(sed -n 's/^ALLOWED_HOSTS=//p' .env | head -1 | cut -d, -f1)"
[ -n "$PRIMARY_HOST" ] || die "ALLOWED_HOSTS is empty in .env — run prepare-server.sh."

# Host port gunicorn is published on. This box runs other apps, so 8000 is not
# guaranteed free. Compose and the nginx site both derive from this value.
APP_PORT="$(sed -n 's/^APP_PORT=//p' .env | head -1)"
APP_PORT="${APP_PORT:-8000}"
export APP_PORT
ok ".env present (primary host: $PRIMARY_HOST, app port: $APP_PORT)."

# Fail early and legibly. Docker's own error for this is a wall of text about
# "failed to bind host port" that reads like a Docker fault rather than
# "another program already owns this port".
if ! docker compose -f "$COMPOSE_FILE" ps --status running --quiet app 2>/dev/null | grep -q .; then
  if ss -ltn 2>/dev/null | grep -qE "[:.]${APP_PORT}[[:space:]]"; then
    warn "Something is already listening on port $APP_PORT:"
    sudo ss -ltnp 2>/dev/null | grep -E "[:.]${APP_PORT}[[:space:]]" || true
    die "Pick a free port: add APP_PORT=<port> to .env and re-run.
     The nginx proxy_pass is rendered from the same value, so both stay in sync."
  fi
fi

# ── 3. Bind-mount dirs (avoid root-owned auto-created dirs) ──────────────────
mkdir -p media staticfiles legacy
ok "media/, staticfiles/ and legacy/ ready."

# ── 4. Docker survives reboot ────────────────────────────────────────────────
log "Enabling Docker at boot..."
sudo systemctl enable --now docker
ok "docker.service enabled."

# ── 5. Bring up the stack ────────────────────────────────────────────────────
log "Building and starting the stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

# ── 6. Wait for app to be healthy ────────────────────────────────────────────
log "Waiting for app to become healthy (migrate + any SQLite import + collectstatic)..."
app_cid="$(docker compose -f "$COMPOSE_FILE" ps -q app)"
[ -n "$app_cid" ] || die "app container did not start. Check: docker compose -f $COMPOSE_FILE logs app"
healthy=0
for i in $(seq 1 30); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$app_cid" 2>/dev/null || echo '')"
  if [ "$status" = "healthy" ]; then healthy=1; break; fi
  printf '  %2d/30 (%s)\n' "$i" "${status:-starting}"
  sleep 5
done
if [ "$healthy" -eq 1 ]; then
  ok "app is healthy."
else
  warn "app not healthy after 150s. Inspect: docker compose -f $COMPOSE_FILE logs app"
fi

# ── 7. Reboot-tolerant systemd unit ──────────────────────────────────────────
log "Installing khab.service (starts the stack on boot)..."
docker_bin="$(command -v docker)"
sudo tee /etc/systemd/system/khab.service >/dev/null <<EOF
[Unit]
Description=KHA Boutique production stack (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_DIR
ExecStart=$docker_bin compose -f $COMPOSE_FILE up -d
ExecStop=$docker_bin compose -f $COMPOSE_FILE down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable khab.service
ok "khab.service enabled. (Containers also have restart: unless-stopped as a backstop.)"

# ── 8. Retire the old socket-based gunicorn ──────────────────────────────────
# If it is still enabled it will grab /run/gunicorn.sock again after a reboot.
for candidate in gunicorn khab-gunicorn gunicorn-khab; do
  if systemctl is-enabled "${candidate}.service" >/dev/null 2>&1; then
    warn "Old unit '${candidate}.service' is still enabled and will start on boot."
    warn "Once you have verified the new stack, retire it with:"
    warn "  sudo systemctl disable --now ${candidate}.service ${candidate}.socket"
  fi
done

# ── 9. Optional host nginx site ──────────────────────────────────────────────
if [ "$WITH_NGINX" -eq 1 ]; then
  SITE=/etc/nginx/sites-available/khab
  # Render __APP_PORT__ so the proxy_pass always matches the port compose
  # actually published. Hand-editing two files that must agree is how you get
  # a 502 that looks like an application fault.
  RENDERED="$(mktemp)"
  sed "s/__APP_PORT__/${APP_PORT}/g" nginx/khab.nginx.conf > "$RENDERED"
  grep -q '__APP_PORT__' "$RENDERED" && die "Failed to substitute APP_PORT into the nginx site."

  if [ -f "$SITE" ] && ! cmp -s "$RENDERED" "$SITE"; then
    BACKUP="${SITE}.pre-docker.$(date +%Y%m%d_%H%M%S)"
    log "Backing up existing site to $BACKUP ..."
    sudo cp "$SITE" "$BACKUP"
    ok "Backup saved (contains the /stofur and /examdata blocks as they were)."
  fi
  log "Installing host nginx site (proxy_pass -> 127.0.0.1:${APP_PORT})..."
  sudo cp "$RENDERED" "$SITE"
  rm -f "$RENDERED"
  sudo ln -sf "$SITE" /etc/nginx/sites-enabled/khab
  if sudo nginx -t; then
    sudo systemctl reload nginx
    ok "nginx config valid and reloaded."
  else
    warn "nginx -t failed — NOT reloading. The old config is still live."
    warn "Fix nginx/khab.nginx.conf, re-run, or restore the backup above."
  fi
fi

# ── 10. Optional superuser ───────────────────────────────────────────────────
if [ "$healthy" -eq 1 ]; then
  read -r -p "Create a Django superuser now? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" exec app python manage.py createsuperuser
  fi
fi

log "Done."
cat <<EOF

Next steps:
  • Verify through nginx:  curl -sI http://$PRIMARY_HOST/login/ | head -1
  • Verify from ANOTHER machine — that is the path users take and it is what
    catches an address missing from ALLOWED_HOSTS.
  • Verify directly:       curl -s -o /dev/null -w '%{http_code}\\n' \\
                             -H 'Host: $PRIMARY_HOST' http://127.0.0.1:$APP_PORT/login/
  • Log in and check /dashboard, /users, /sales, /scoreboard
  • If data was imported, confirm the counts, then: rm -rf legacy/
  • Retire the old gunicorn unit (see warning above, if any)
  • Future deploys:        ./scripts/deploy.sh
EOF
