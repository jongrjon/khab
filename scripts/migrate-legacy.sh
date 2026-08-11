#!/usr/bin/env bash
#
# migrate-legacy.sh — carry the live SQLite database and media over from the
# old /var/www/khab install into /srv/khab, one time, before init-server.sh.
#
# It COPIES. Nothing under /var/www/khab is modified or deleted, so the old
# install stays intact as the rollback path.
#
# The old app must be stopped while the database is copied: SQLite writes
# across three files (db, -wal, -shm) and copying a live one can capture a
# torn state. --keep-running skips the stop if you have already done it.
#
# Usage:
#   ./scripts/migrate-legacy.sh [--from /var/www/khab] [--service gunicorn]
#                               [--keep-running]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LEGACY_DIR="/var/www/khab"
OLD_SERVICE=""
STOP_OLD=1

while [ $# -gt 0 ]; do
  case "$1" in
    --from)         LEGACY_DIR="${2:?--from needs a path}"; shift 2 ;;
    --service)      OLD_SERVICE="${2:?--service needs a name}"; shift 2 ;;
    --keep-running) STOP_OLD=0; shift ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

log(){  printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok(){   printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){  printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

cd "$REPO_DIR"
[ -d "$LEGACY_DIR" ] || die "$LEGACY_DIR not found. Use --from if the old install is elsewhere."
[ -f "$LEGACY_DIR/db.sqlite3" ] || die "$LEGACY_DIR/db.sqlite3 not found — nothing to migrate."

# ── 1. Refuse to run if Postgres already holds data ──────────────────────────
# The entrypoint's import is guarded by "user table is empty", so a second run
# would silently do nothing and look like it worked. Say so plainly instead.
if docker compose -f docker-compose.prod.yaml ps --status running --quiet db 2>/dev/null | grep -q .; then
  existing="$(docker compose -f docker-compose.prod.yaml exec -T db \
      psql -U khab -d khab -tAc 'SELECT COUNT(*) FROM auth_user' 2>/dev/null || echo 0)"
  if [ "${existing:-0}" -gt 0 ]; then
    die "Postgres already has $existing users. The SQLite import only runs into an
       empty database, so this would be a no-op. To genuinely start over:
         docker compose -f docker-compose.prod.yaml down -v   # DESTROYS the volume"
  fi
fi

# ── 2. Find and stop the old gunicorn ────────────────────────────────────────
# The old nginx proxied to unix:/run/gunicorn.sock, so there is a systemd unit
# holding that socket. Name is usually gunicorn.service (+ gunicorn.socket).
if [ -z "$OLD_SERVICE" ]; then
  for candidate in gunicorn khab gunicorn-khab; do
    if systemctl list-unit-files "${candidate}.service" --no-legend 2>/dev/null | grep -q .; then
      OLD_SERVICE="$candidate"
      break
    fi
  done
fi

if [ "$STOP_OLD" -eq 1 ]; then
  if [ -n "$OLD_SERVICE" ]; then
    log "Stopping old app ($OLD_SERVICE) for a consistent database copy..."
    sudo systemctl stop "${OLD_SERVICE}.socket" 2>/dev/null || true
    sudo systemctl stop "${OLD_SERVICE}.service"
    ok "$OLD_SERVICE stopped. (Site is down until init-server.sh finishes.)"
  else
    warn "No gunicorn unit found automatically."
    warn "Pass --service <name>, or stop the old app yourself and re-run with --keep-running."
    die  "Refusing to copy a live SQLite database."
  fi
else
  warn "--keep-running: assuming you already stopped the old app."
fi

# ── 3. Copy the database ─────────────────────────────────────────────────────
mkdir -p legacy
log "Copying database from $LEGACY_DIR ..."
cp "$LEGACY_DIR/db.sqlite3" legacy/db.sqlite3
# -wal / -shm only exist if the old app used WAL mode and exited uncleanly.
for suffix in -wal -shm; do
  [ -f "$LEGACY_DIR/db.sqlite3$suffix" ] && cp "$LEGACY_DIR/db.sqlite3$suffix" "legacy/db.sqlite3$suffix"
done
ok "legacy/db.sqlite3 copied ($(du -h legacy/db.sqlite3 | cut -f1))."

# ── 4. Sanity-check it before trusting the import ────────────────────────────
log "Checking the copy..."
python3 - <<'PY'
import sqlite3, sys

conn = sqlite3.connect("legacy/db.sqlite3")
conn.row_factory = sqlite3.Row
required = ["auth_user", "boutique_product", "boutique_sale",
            "boutique_payment", "boutique_invite"]
present = {r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}

missing = [t for t in required if t not in present]
if missing:
    sys.exit(f"  Missing tables in the copy: {', '.join(missing)}")

for table in required:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"    {table:20} {n:>7}")

if conn.execute("SELECT COUNT(*) FROM auth_user").fetchone()[0] == 0:
    sys.exit("  auth_user is empty — that is not the live database.")
conn.close()
PY
ok "Copy looks sound."

# ── 5. Copy media ────────────────────────────────────────────────────────────
if [ -d "$LEGACY_DIR/media" ]; then
  log "Copying media/ ..."
  mkdir -p media
  cp -r "$LEGACY_DIR/media/." media/
  ok "media/ copied ($(du -sh media | cut -f1))."
else
  warn "$LEGACY_DIR/media not found — skipping media."
fi

# Old static/ is deliberately NOT copied: collectstatic regenerates
# staticfiles/ from the repo on every container start.

cat <<EOF

$(printf '\033[1;32m  ✓\033[0m') Legacy data staged.

  The stack import runs automatically on first start, but only while the
  Postgres user table is empty. Next:

    ./scripts/init-server.sh --with-nginx

  Watch for "First run detected: migrating data from SQLite" in the log.
  Once the row counts above match what the app shows, delete legacy/:

    rm -rf $REPO_DIR/legacy

  The old install at $LEGACY_DIR is untouched — that is your rollback.
EOF
