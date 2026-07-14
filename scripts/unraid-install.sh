#!/bin/bash
# Build and start the SubFly server image on Unraid.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$ROOT/server"

cd "$SERVER_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created server/.env — edit MEDIA_PATH and SUBFLY_PATH_MAPS before first run."
fi

echo "Building subfly-server image..."
docker compose build

echo "Starting SubFly server..."
docker compose up -d

echo
echo "Waiting for health..."
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8765/healthz >/dev/null 2>&1; then
    curl -sS http://127.0.0.1:8765/healthz
    echo
    echo "SubFly server is up on port 8765"
    exit 0
  fi
  sleep 5
done

echo "Service did not become healthy in time. Check: docker logs subfly" >&2
exit 1
