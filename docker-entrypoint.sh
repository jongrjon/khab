#!/bin/bash
set -e

echo "=== KHA Boutique startup ==="

# --- Wait for database ---
echo "Waiting for database..."
while ! python -c "
import dj_database_url, os, psycopg2
url = os.environ.get('DATABASE_URL', '')
if 'postgres' in url:
    params = dj_database_url.parse(url)
    psycopg2.connect(dbname=params['NAME'], user=params['USER'], password=params['PASSWORD'], host=params['HOST'], port=params['PORT'])
" 2>/dev/null; do
    echo "  Database not ready, waiting..."
    sleep 2
done
echo "Database is ready."

# --- Run migrations ---
echo "Running migrations..."
python manage.py migrate --noinput

# --- First-run: migrate data from SQLite if available ---
USER_COUNT=$(python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'khab.settings')
django.setup()
from django.contrib.auth.models import User
print(User.objects.count())
")

# legacy/db.sqlite3 is a read-only bind mount (see docker-compose.prod.yaml),
# so the file no longer has to be baked into the image. The old deploy script
# used to strip db.sqlite3 out of .dockerignore to smuggle it in.
# The bare db.sqlite3 fallback keeps older local setups working.
LEGACY_DB=""
for candidate in /app/legacy/db.sqlite3 db.sqlite3; do
    [ -f "$candidate" ] && { LEGACY_DB="$candidate"; break; }
done

if [ "$USER_COUNT" = "0" ] && [ -n "$LEGACY_DB" ]; then
    echo "=== First run detected: migrating data from SQLite ($LEGACY_DB) ==="
    LEGACY_DB="$LEGACY_DB" python -c "
import sqlite3, json, os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'khab.settings')
django.setup()

conn = sqlite3.connect(os.environ['LEGACY_DB'])
conn.row_factory = sqlite3.Row
fixtures = []

# auth_user with groups
for row in conn.execute('SELECT * FROM auth_user'):
    groups = [r['group_id'] for r in conn.execute('SELECT group_id FROM auth_user_groups WHERE user_id=?', (row['id'],))]
    fixtures.append({
        'model': 'auth.user', 'pk': row['id'],
        'fields': {
            'password': row['password'], 'last_login': row['last_login'],
            'is_superuser': bool(row['is_superuser']), 'username': row['username'],
            'first_name': row['first_name'], 'last_name': row['last_name'],
            'email': row['email'], 'is_staff': bool(row['is_staff']),
            'is_active': bool(row['is_active']), 'date_joined': row['date_joined'],
            'groups': groups, 'user_permissions': [],
        }
    })

# boutique_product
for row in conn.execute('SELECT * FROM boutique_product'):
    fixtures.append({
        'model': 'boutique.product', 'pk': row['id'],
        'fields': {
            'name': row['name'], 'prod_img': row['prod_img'],
            'price': row['price'], 'active': bool(row['active']),
        }
    })

# boutique_sale
for row in conn.execute('SELECT * FROM boutique_sale'):
    fixtures.append({
        'model': 'boutique.sale', 'pk': row['id'],
        'fields': {
            'buyer': row['buyer_id'], 'product': row['product_id'],
            'price': row['price'], 'saletime': row['saletime'],
        }
    })

# boutique_payment
for row in conn.execute('SELECT * FROM boutique_payment'):
    fixtures.append({
        'model': 'boutique.payment', 'pk': row['id'],
        'fields': {
            'payer': row['payer_id'], 'amount': row['amount'],
            'paytime': row['paytime'],
        }
    })

# boutique_invite
for row in conn.execute('SELECT * FROM boutique_invite'):
    fixtures.append({
        'model': 'boutique.invite', 'pk': row['id'],
        'fields': {
            'invited': row['invited'], 'timeout': row['timeout'],
        }
    })

conn.close()

with open('/tmp/khab_migration.json', 'w') as f:
    json.dump(fixtures, f, ensure_ascii=False)

print(f'Exported {len(fixtures)} objects from SQLite')
"
    echo "Loading data into PostgreSQL..."
    python manage.py loaddata /tmp/khab_migration.json 2>&1 | tail -1
    rm -f /tmp/khab_migration.json
    echo "SQLite migration complete."
fi

# --- Fetch staff avatars if any profiles are missing images ---
MISSING_AVATARS=$(python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'khab.settings')
django.setup()
from boutique.models import UserProfile
print(UserProfile.objects.filter(profile_img='').count())
")

# Some accounts (shared mailboxes, ex-staff) have no photo on unak.is and never
# will, so MISSING_AVATARS never reaches 0 and this would scrape the site on
# every single container start, delaying gunicorn on every deploy. Set
# SKIP_AVATAR_FETCH=1 in .env once the initial import has run; fetch new
# avatars on demand with:
#   docker compose -f docker-compose.prod.yaml exec app python manage.py fetch_avatars
if [ "${SKIP_AVATAR_FETCH:-0}" = "1" ]; then
    echo "Skipping avatar fetch (SKIP_AVATAR_FETCH=1)."
elif [ "$MISSING_AVATARS" -gt "0" ]; then
    echo "=== Fetching $MISSING_AVATARS missing staff avatars ==="
    python manage.py fetch_avatars 2>&1 || echo "Avatar fetch failed (non-critical), continuing..."
fi

# --- Collect static files ---
echo "Collecting static files..."
python manage.py collectstatic --noinput

# --- Start gunicorn ---
echo "Starting gunicorn..."
# 0.0.0.0 inside the container is fine — docker-compose.prod.yaml publishes it
# to 127.0.0.1 only, so nginx is the sole reachable client.
exec gunicorn khab.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
