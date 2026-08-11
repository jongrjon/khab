# KHA Boutique — Deployment

Production lives in **`/srv/khab`** on the dev box, runs as a Docker Compose
stack, and is fronted by the host nginx. It is reached **by IP** — there is no
hostname, and HTTP only, internal.

Three scripts, in order. The first two run once; the third is every deploy after.

| Script | When | What it does |
|---|---|---|
| `scripts/prepare-server.sh` | once | prereqs, clone to `/srv/khab`, docker group, sudoers, `.env` |
| `scripts/migrate-legacy.sh` | once | copies the live SQLite DB + media out of `/var/www/khab` |
| `scripts/init-server.sh` | once | builds, starts, health-gates, `khab.service`, nginx site |
| `scripts/deploy.sh` | every deploy | pull → build → recreate → health-gate → reload nginx |

---

## A. What this replaces

The old setup, live since 2023:

- SQLite on disk at `/var/www/khab/db.sqlite3`
- gunicorn from a systemd unit on `unix:/run/gunicorn.sock`
- `DEBUG = True`, `ALLOWED_HOSTS = ["*"]`, `SECRET_KEY` hardcoded in source
- nginx serving `/static`, `/media` **and `/templates`** with `autoindex on`
- no backups

Everything above changes. The old install is **left on disk untouched** so it
stays available as a rollback.

---

## B. First-time cutover

Run as your normal user (`jonhelgi`), not root.

### 1. Rotate the leaked Gmail app password — do this first

`khab/emailsettings.py` committed the app password for `khaverslun@gmail.com`
to a **public** GitHub repo in 2023. Revoke it at
<https://myaccount.google.com/apppasswords>, generate a new one, and keep it
handy for step 2. `prepare-server.sh` refuses to continue if it finds the old
value.

### 2. Prereqs and clone

```bash
curl -O https://raw.githubusercontent.com/jongrjon/khab/master/scripts/prepare-server.sh
bash prepare-server.sh
```

It creates `/srv/khab`, clones into it, adds you to the `docker` group, installs
a sudoers rule for `systemctl reload nginx`, and writes `.env` with generated
`SECRET_KEY` and `POSTGRES_PASSWORD`. It then **stops** and lists what you must
fill in by hand (the email credentials). Fill them in, re-run to verify.

If it added you to the `docker` group, log out and back in before continuing.

### 3. Carry the live data over

```bash
cd /srv/khab
./scripts/migrate-legacy.sh
```

This **stops the old gunicorn** (the site goes down here), copies
`/var/www/khab/db.sqlite3` into `legacy/`, sanity-checks the tables and row
counts, and copies `media/` over. It only ever reads from `/var/www/khab`.

The database has to be stopped during the copy: SQLite spreads writes across
`db`, `-wal` and `-shm`, and copying a live one can capture a torn state.

If the script can't find the old systemd unit, pass `--service <name>`.

### 4. Build and start

```bash
./scripts/init-server.sh --with-nginx
```

Builds the image, starts `app` + `db` + `backup`, waits for the health gate,
installs `khab.service` so the stack survives reboots, and swaps in the nginx
site (backing up the existing one to
`/etc/nginx/sites-available/khab.pre-docker.<timestamp>` first).

On first start the entrypoint sees an empty Postgres plus `legacy/db.sqlite3`
and imports everything — users with their groups, products, sales, payments,
invites. Watch for `First run detected: migrating data from SQLite`.

### 5. Verify, then clean up

```bash
IP="$(sed -n 's/^ALLOWED_HOSTS=//p' .env | cut -d, -f1)"
curl -sI "http://$IP/login/" | head -1                  # 200
docker compose -f docker-compose.prod.yaml ps           # app healthy, db healthy
```

Check it from another machine too, not just the box — that is the path users
take, and it is what catches an address missing from `ALLOWED_HOSTS`.

Log in and check `/dashboard`, `/users`, `/sales`, `/scoreboard`. Confirm the
row counts match what `migrate-legacy.sh` printed. Then:

```bash
rm -rf /srv/khab/legacy                                  # importer input, no longer needed
sudo systemctl disable --now gunicorn.service gunicorn.socket
echo "SKIP_AVATAR_FETCH=1" >> .env && ./scripts/deploy.sh
```

Leave `/var/www/khab` alone for a few weeks as the rollback.

---

## C. Routine deploys

```bash
cd /srv/khab && ./scripts/deploy.sh
```

Pull, build, recreate, health-gate, reload nginx. If the new container never
reports healthy the script prints the exact `git reset --hard <sha>` to roll
back — but note that a migration which already applied is **not** undone by
that reset.

Flags: `--no-nginx` (skip the reload), `--branch <name>`.

---

## D. Rollback to the old setup

Nothing in the cutover is destructive, so:

```bash
cd /srv/khab && docker compose -f docker-compose.prod.yaml down
sudo cp /etc/nginx/sites-available/khab.pre-docker.<timestamp> /etc/nginx/sites-available/khab
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now gunicorn.service gunicorn.socket
```

Anything written in the new stack after cutover stays in Postgres and does not
travel back to SQLite.

---

## E. Common operations

```bash
cd /srv/khab
C="docker compose -f docker-compose.prod.yaml"

$C logs -f app                       # application logs
$C ps                                # health status
$C restart app

$C exec app python manage.py createsuperuser
$C exec app python manage.py fetch_avatars          # new staff photos
$C exec db psql -U khab -d khab                     # psql (no host port exposed)

$C exec backup /scripts/backup.sh    # manual backup; otherwise daily, 30-day retention
$C exec backup ls /backups
./scripts/restore.sh /backups/khab_<timestamp>.sql.gz
```

---

## F. Architecture

```
                  http://<server-ip>:80  (default_server, no hostname)
                             │
                    ┌────────▼────────┐
                    │   host nginx    │  /static/ → /srv/khab/staticfiles/
                    │                 │  /media/  → /srv/khab/media/
                    └────────┬────────┘  /stofur, /examdata → unchanged, being retired
                             │ proxy_pass 127.0.0.1:$APP_PORT
   ╔═════════════════════════▼═══════════════════════════╗
   ║  /srv/khab   docker compose -f docker-compose.prod   ║
   ║                                                      ║
   ║   app ──────────────▶ db ◀────────── backup          ║
   ║   gunicorn ×3         postgres 16     daily pg_dump  ║
   ║   127.0.0.1:$APP_PORT   no host port    30-day keep    ║
   ╚══════════════════════════════════════════════════════╝
        │                    │                  │
    ./media              postgres_data      backup_data
    ./staticfiles         (volume)           (volume)
```

Deliberate choices:

- **`app` publishes on `127.0.0.1:$APP_PORT`** (`APP_PORT` in `.env`, default 8000), not `0.0.0.0`. nginx is the only
  client; there is no way to reach gunicorn from off-box.
- **`db` publishes no host port at all.** Use `exec db psql` to get in.
- **The healthcheck sends the real hostname** as its `Host` header rather than
  `localhost`. Hitting loopback by name makes Django return 400 unless
  `localhost` is in `ALLOWED_HOSTS` — which both hides a broken
  `ALLOWED_HOSTS` (container reports healthy while every real request 400s)
  and pushes loopback entries into production config.
- **`/templates` is gone from nginx.** It served the raw Django template
  directory with directory listing enabled.
- **`autoindex` is off** for `/static/` and `/media/`; the old config let
  anyone browse every staff avatar and product image.
- **`listen 80 default_server` is kept, and it is what makes IP access work.**
  The app has no hostname; requests arrive at the box's address and match no
  `server_name`, so nginx hands them to the default server. `server_name` is
  `_` for that reason. Remove `default_server` and IP traffic goes to whichever
  other vhost nginx picks first.
- **`ALLOWED_HOSTS` is the one setting that can silently take the site down.**
  nginx will happily accept any `Host`; Django is what rejects it. With
  `DEBUG=False`, an address that is not listed returns 400 for every request.
  `prepare-server.sh` detects the box's addresses and writes them, first entry
  being the primary route address — which is also the `Host` the healthcheck
  sends, so a broken list fails the deploy gate instead of going live.

---

## G. Local development

Unrelated to the above; uses `docker-compose.yml`, not `docker-compose.prod.yaml`.

```bash
docker compose up --build -d      # app :8000, db :5433, plus local nginx if you have an override
```

A `docker-compose.override.yml` is picked up automatically and is gitignored —
use it for machine-specific port remaps. Note Compose *appends* `ports` lists
when merging; use `ports: !override` to replace instead.

For template and CSS work, `pipenv run python manage.py runserver` is the
faster loop — it serves static files itself, so no nginx is needed.
