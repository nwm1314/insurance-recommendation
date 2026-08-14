#!/bin/sh
set -eu

cd /srv/backend
alembic upgrade head

cd /srv
exec "$@"
