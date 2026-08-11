# KHA Boutique

Internal staff boutique/shop application for the organization KHA. Staff purchase products, admins manage inventory, payments, and users.

## Tech Stack

- **Backend:** Django 5.2 LTS (Python 3.12) — versions pinned in `Pipfile.lock`
- **Database:** PostgreSQL (via docker-compose)
- **Frontend:** Bootstrap 5 + jQuery
- **Server:** Gunicorn
- **Containerization:** Docker + docker-compose
- **Dependency Management:** Pipenv
- **Config:** python-decouple (.env files)

## UI Language

All user-facing text is in **Icelandic**. Keep this consistent.

## User Roles (Django Groups)

- **`person`** — Regular staff member. Can purchase items, view own status/history.
- **`vendor`** — Kiosk/display account. Can make purchases on behalf of staff members.
- **superuser** — Admin. Manages products, sales, payments, users, invites.

## Data Models

- **Product** — name, image, price, active flag
- **Sale** — links buyer (User) to product with price and timestamp
- **Payment** — tracks payments made by users (amount + timestamp)
- **Invite** — email-based invite tokens for new user registration (24h timeout)

## Key Directories

```
khab/           — Django project config (settings, urls, wsgi)
boutique/       — Main app (models, views, urls, templates, admin)
static/         — Bootstrap CSS/JS + custom boutique.css
templates/      — Global templates (registration/login flow)
gunicorn/       — Gunicorn config
scripts/        — Utility scripts (backups, etc.)
```

## Running Locally

```bash
# With pipenv
pipenv install
pipenv run python manage.py migrate
pipenv run python manage.py runserver

# With Docker
docker compose up
```

## Environment Variables

All configuration is via `.env` file (see `.env.example` for required variables). Never commit secrets.

## Development Commands

```bash
pipenv run python manage.py makemigrations   # After model changes
pipenv run python manage.py migrate          # Apply migrations
pipenv run python manage.py createsuperuser  # Create admin user
pipenv run python manage.py collectstatic    # Collect static files
```
