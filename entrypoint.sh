#!/usr/bin/env bash
# ── Backend konteyner ishga tushishi ─────────────────────────────────────────
# 1) PostgreSQL tayyor bo'lguncha kutadi
# 2) migratsiyalarni qo'llaydi
# 3) static fayllarni yig'adi (admin panel uchun)
# 4) ixtiyoriy: superuser yaratadi (DJANGO_SUPERUSER_* env berilgan bo'lsa)
set -e

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:=kutubxona}"
: "${DB_ENGINE:=postgres}"

if [ "$DB_ENGINE" = "postgres" ]; then
  echo "→ PostgreSQL kutilmoqda ($POSTGRES_HOST:$POSTGRES_PORT)…"
  for i in $(seq 1 60); do
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" >/dev/null 2>&1; then
      echo "→ PostgreSQL tayyor."
      break
    fi
    if [ "$i" = "60" ]; then
      echo "✗ PostgreSQL 60 soniyada javob bermadi." >&2
      exit 1
    fi
    sleep 1
  done
fi

echo "→ Migratsiyalar…"
python manage.py migrate --noinput

echo "→ Static fayllar…"
python manage.py collectstatic --noinput --clear >/dev/null

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "→ Superuser tekshirilmoqda ($DJANGO_SUPERUSER_USERNAME)…"
  python manage.py createsuperuser --noinput 2>/dev/null \
    && echo "  superuser yaratildi" \
    || echo "  superuser allaqachon mavjud"
fi

echo "→ Ishga tushmoqda: $*"
exec "$@"
