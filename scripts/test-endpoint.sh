#!/usr/bin/env bash
set -Eeuo pipefail
HOST="${1:-127.0.0.1}"
PORT="${2:-8443}"
BASE="https://${HOST}:${PORT}"

echo "== Health (expected 200) =="
curl -ksS -o /dev/null -w '%{http_code}\n' "${BASE}/health"

echo "== MCP without token (expected 401) =="
curl -ksS -o /dev/null -w '%{http_code}\n' \
  -X POST "${BASE}/mcp" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'
