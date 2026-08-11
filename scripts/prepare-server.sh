#!/usr/bin/env bash
#
# prepare-server.sh — one-time prod prerequisites + clone for KHA Boutique.
#
# Run this ON THE DEV BOX as your non-root deploy user (the one that will own
# /srv/khab). Idempotent — safe to re-run. It does the manual bits that
# scripts/init-server.sh does NOT: dir ownership, clone, docker group,
# passwordless nginx reload, and .env. It STOPS after creating .env so you can
# fill in the secrets it cannot derive, then you re-run to continue.
#
# Values it can derive (domain, DEBUG, generated secrets) are WRITTEN into .env
# directly, never printed for you to paste — hand-pasting onto a line that
# already had the key is how you end up with "ALLOWED_HOSTS=ALLOWED_HOSTS=..."
# and a Django that 400s every request while the healthcheck stays green.
#
# After this succeeds:
#   ./scripts/migrate-legacy.sh          # carry the live SQLite data over
#   ./scripts/init-server.sh --with-nginx
#
set -euo pipefail

# HTTPS, not SSH: the prod box only ever reads, and the repo is public, so it
# needs no deploy key. Switch to git@github.com:jongrjon/khab.git if the repo
# is ever made private — then the box needs its own SSH key.
REPO_URL="https://github.com/jongrjon/khab.git"
TARGET="/srv/khab"

# The site is reached by IP, not by a hostname, so ALLOWED_HOSTS is detected
# from the box's own interfaces rather than hardcoded. Add extras (a second IP,
# a hostname you actually use) with --host, repeatable.
EXTRA_HOSTS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --host) EXTRA_HOSTS+=("${2:?--host needs a value}"); shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

# The Gmail app password that sat in khab/emailsettings.py in a PUBLIC repo
# from 2023 until this refactor. Treated as burned; must not be reused.
LEAKED_EMAIL_PW="xohijpzjagwvzgzk"

log(){  printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok(){   printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){  printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "Run as your non-root deploy user, not root."

# detect_hosts — every name/address this box can legitimately be reached at,
# primary route address first (the healthcheck uses entry #1 as its Host
# header). Order-preserving dedupe; blanks dropped.
detect_hosts(){
  {
    ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*[[:space:]]src[[:space:]]\([0-9.]*\).*/\1/p'
    # Skip docker0 / br-* / veth* — nobody reaches the site on a bridge address,
    # and they change every time the compose network is recreated.
    ip -4 -o addr show scope global 2>/dev/null |
      awk '$2 !~ /^(docker|br-|veth)/ {split($4,a,"/"); print a[1]}'
    hostname 2>/dev/null
    hostname -f 2>/dev/null
    printf '%s\n' "${EXTRA_HOSTS[@]+"${EXTRA_HOSTS[@]}"}"
  } | awk 'NF && !seen[$0]++' | paste -sd, -
}

# set_env KEY VALUE — replace the line in place, or append if absent.
# python3 rather than sed so values containing / & \ are safe, and so it can
# never emit a duplicated "KEY=KEY=" prefix.
set_env(){
  K="$1" V="$2" python3 - <<'PY'
import os

key, value = os.environ["K"], os.environ["V"]
path = ".env"
with open(path) as fh:
    lines = fh.read().splitlines()

prefix = key + "="
for i, line in enumerate(lines):
    if line.startswith(prefix):
        lines[i] = prefix + value
        break
else:
    lines.append(prefix + value)

with open(path, "w") as fh:
    fh.write("\n".join(lines) + "\n")
PY
}

# env_value KEY — current value in .env, empty if unset.
env_value(){ sed -n "s/^$1=//p" .env | head -1; }

# is_placeholder VALUE — true if the value is a stand-in rather than a real
# secret. .env.example ships "generate-me"; Django's startproject emits the
# "django-insecure-" prefix. Keep this in sync with .env.example: a placeholder
# that is not listed here gets silently accepted as a real secret.
is_placeholder(){
  case "${1:-}" in
    ''|*generate-me*|*generate_me*|*your*|*YOUR*|*change*|*CHANGE*) return 0 ;;
    *example*|*EXAMPLE*|*insecure*|*placeholder*|*fill-me*|*TODO*)  return 0 ;;
  esac
  return 1
}

# ── 1. Prerequisites ─────────────────────────────────────────────────────────
log "Checking prerequisites..."
for bin in docker git python3; do
  command -v "$bin" >/dev/null 2>&1 || die "'$bin' is not installed or not on PATH."
done
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) is not available."
ok "docker, git, python3 present."
# No Node here, unlike smha — khab has no frontend build step.

# ── 2. Own the target dir (git never runs as root) ───────────────────────────
if [ ! -d "$TARGET/.git" ]; then
  log "Creating and taking ownership of $TARGET ..."
  sudo mkdir -p "$TARGET"
  sudo chown "$USER:$USER" "$TARGET"
  log "Cloning $REPO_URL ..."
  git clone "$REPO_URL" "$TARGET"
  ok "Cloned to $TARGET."
else
  ok "$TARGET already a git repo — pulling latest."
  git -C "$TARGET" pull --ff-only origin master
fi
cd "$TARGET"
ok "On commit $(git rev-parse --short HEAD)."

# nginx (as www-data) has to traverse /srv/khab to reach staticfiles/ and media/.
chmod 755 "$TARGET"
ok "$TARGET is traversable by nginx."

# ── 3. docker group (so docker compose runs without sudo) ────────────────────
if ! groups | grep -qw docker; then
  log "Adding $USER to docker group..."
  sudo usermod -aG docker "$USER"
  ok "Added to docker group — LOG OUT AND BACK IN before running init-server.sh."
else
  ok "Already in docker group."
fi

# ── 4. Passwordless nginx reload for deploy.sh ───────────────────────────────
SUDOERS=/etc/sudoers.d/khab-deploy
if [ ! -f "$SUDOERS" ]; then
  log "Installing sudoers rule for 'systemctl reload nginx'..."
  echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx" | sudo tee "$SUDOERS" >/dev/null
  sudo chmod 440 "$SUDOERS"
  ok "Sudoers rule installed."
else
  ok "Sudoers rule already present."
fi

# ── 5. .env — derivable values written here, secrets left for you ────────────
if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env created from .env.example."
fi

log "Writing derived production values into .env ..."
set_env DEBUG False

# The site is reached by IP. With DEBUG=False, Django 400s any request whose
# Host header is not in this list, so every address people actually type has to
# be here — this is the one setting that silently takes the site down if it is
# wrong. No loopback entries: the healthcheck sends entry #1 as its Host
# header, so it exercises the same list real traffic does.
HOSTS="$(detect_hosts)"
[ -n "$HOSTS" ] || die "Could not detect any address for this box. Pass --host <ip> explicitly."
set_env ALLOWED_HOSTS "$HOSTS"
ok "DEBUG=False, ALLOWED_HOSTS=$HOSTS"
warn "If you reach the app at an address not in that list, add it: --host <addr>"

# Also regenerate anything shorter than Django's own 50-character threshold —
# rotating SECRET_KEY only invalidates existing sessions, so erring towards
# regeneration is cheap.
CURRENT_SECRET="$(env_value SECRET_KEY)"
if is_placeholder "$CURRENT_SECRET" || [ "${#CURRENT_SECRET}" -lt 50 ]; then
  set_env SECRET_KEY "$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  ok "SECRET_KEY generated."
else
  ok "SECRET_KEY already set — left alone."
fi

# No length check here, unlike SECRET_KEY: Postgres keeps whatever password the
# volume was initialised with, so silently rotating this would lock the app out
# of an existing database.
CURRENT_PGPW="$(env_value POSTGRES_PASSWORD)"
if is_placeholder "$CURRENT_PGPW" || [ "$CURRENT_PGPW" = "khab" ]; then
  set_env POSTGRES_PASSWORD "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  ok "POSTGRES_PASSWORD generated."
  if docker volume ls -q 2>/dev/null | grep -qx 'khab_postgres_data'; then
    warn "A khab_postgres_data volume already exists, and the password just changed."
    warn "Postgres keeps the password from first init, so the app will fail to"
    warn "authenticate. Either restore the previous value in .env, or wipe the"
    warn "volume:  docker compose -f docker-compose.prod.yaml down -v"
  fi
else
  ok "POSTGRES_PASSWORD already set — left alone."
fi

# docker-compose.prod.yaml overrides this for the container. Kept in sync here
# so the file is not self-contradictory; the db has no host port in prod, so
# this URL is not reachable from the host anyway.
set_env DATABASE_URL "postgres://khab:$(env_value POSTGRES_PASSWORD)@db:5432/khab"

# ── 6. Secrets that cannot be derived ────────────────────────────────────────
if [ "$(env_value EMAIL_HOST_PASSWORD)" = "$LEAKED_EMAIL_PW" ]; then
  cat >&2 <<EOF

$(printf '\033[1;31m[err]\033[0m') EMAIL_HOST_PASSWORD is the app password that was committed to
      khab/emailsettings.py in a PUBLIC GitHub repo in 2023. It has been
      readable by anyone for years and must be revoked, not reused.

      1. https://myaccount.google.com/apppasswords  — revoke the old one
      2. Generate a new app password for khaverslun@gmail.com
      3. Put the new value in $TARGET/.env
      4. Re-run this script

EOF
  exit 1
fi

MISSING=""
for key in SECRET_KEY POSTGRES_PASSWORD EMAIL_HOST_USER EMAIL_HOST_PASSWORD; do
  is_placeholder "$(env_value "$key")" && MISSING="$MISSING $key"
done

if [ -n "$MISSING" ]; then
  printf '\n\033[1;33mACTION NEEDED:\033[0m fill in these values in %s/.env\n' "$TARGET"
  for key in $MISSING; do printf '  %s\n' "$key"; done
  printf '\nEdit with nano, then RE-RUN this script to verify.\n'
  exit 0
fi
ok "All required .env values present."

chmod 600 .env
ok ".env locked to 0600."

log "Prereqs complete. Next:"
printf '  cd %s\n' "$TARGET"
printf '  ./scripts/migrate-legacy.sh          # carry live SQLite + media over\n'
printf '  ./scripts/init-server.sh --with-nginx\n'
[ -d /var/www/khab ] || warn "/var/www/khab not found — skip migrate-legacy.sh if there is no old install."
