#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB="${ROOT}/secrets/monitor_ed25519.pub"
[[ -f "${PUB}" ]] || { echo "Missing ${PUB}; run init-secrets.sh first." >&2; exit 1; }
printf 'restrict %s\n' "$(cat "${PUB}")"
