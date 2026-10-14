#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN="${ROOT}/secrets/mcp_bearer_token"
if [[ -r "${TOKEN}" ]]; then
  cat "${TOKEN}"; echo
else
  sudo cat "${TOKEN}"; echo
fi
