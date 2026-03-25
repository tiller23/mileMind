#!/bin/sh
# Run Alembic migrations before starting the server.
# Used as Railway deploy command or Docker entrypoint.
set -e
cd /app
alembic upgrade head
echo "Migrations complete."
