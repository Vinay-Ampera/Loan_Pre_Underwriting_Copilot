#!/bin/sh
# Container start (Stage 11): bring the database up to date, then start the server.
# Every step is safe to repeat: migrations apply only what is new, the seed upserts the rules
# and mock records, and the re-index imports only policy files whose version label is new.
set -eu

cd /app/backend

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is empty: fill it in .env (see .env.example)" >&2
  exit 1
fi

echo "waiting for the database"
tries=0
until python -c "
from sqlalchemy import create_engine, text
from app.core.config import get_settings
with create_engine(get_settings().sqlalchemy_url()).connect() as c:
    c.execute(text('SELECT 1'))
" >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    echo "the database did not answer after a minute; check DATABASE_URL" >&2
    python -m app.db.check || true
    exit 1
  fi
  sleep 2
done

python -m app.db.migrate
python -m app.db.seed
python -m app.rag.reindex

exec "$@"
