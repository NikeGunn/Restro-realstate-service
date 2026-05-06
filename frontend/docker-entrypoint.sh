#!/bin/sh
# Frontend container entrypoint.
#
# Auto-syncs node_modules with package.json on every container start so that:
# - Adding a dependency to package.json on the host → restart container → it
#   installs automatically. No need to remember `docker compose exec frontend
#   npm install`.
# - The anonymous/named node_modules volume can outlive package.json edits
#   without breaking the dev server.
#
# Strategy: hash package.json + package-lock.json (if present) and compare to a
# marker file inside node_modules. If different (or missing), run npm install.
set -e

cd /app

MARKER="node_modules/.deps.hash"
# md5sum is in busybox on alpine; sha256sum is also fine if available.
HASH_INPUT="package.json"
[ -f package-lock.json ] && HASH_INPUT="$HASH_INPUT package-lock.json"

# shellcheck disable=SC2086
CURRENT_HASH=$(cat $HASH_INPUT 2>/dev/null | md5sum | awk '{print $1}')

NEEDS_INSTALL=0
if [ ! -d node_modules ] || [ -z "$(ls -A node_modules 2>/dev/null)" ]; then
  echo "[entrypoint] node_modules missing — running npm install"
  NEEDS_INSTALL=1
elif [ ! -f "$MARKER" ]; then
  echo "[entrypoint] dependency hash marker missing — running npm install"
  NEEDS_INSTALL=1
elif [ "$(cat "$MARKER" 2>/dev/null)" != "$CURRENT_HASH" ]; then
  echo "[entrypoint] package.json changed since last install — running npm install"
  NEEDS_INSTALL=1
fi

if [ "$NEEDS_INSTALL" = "1" ]; then
  npm install --legacy-peer-deps
  echo "$CURRENT_HASH" > "$MARKER"
  echo "[entrypoint] dependencies in sync"
else
  echo "[entrypoint] dependencies already in sync — skipping npm install"
fi

exec "$@"
