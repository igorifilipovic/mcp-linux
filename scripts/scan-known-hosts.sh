#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

[[ -f config/targets.yaml ]] || { echo "Missing config/targets.yaml" >&2; exit 1; }
# Compose bind mounts require the source path to exist. The scanner itself does not trust this file.
touch config/known_hosts

docker compose build ito-linux-monitor-mcp >/dev/null

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

docker compose run --rm --no-deps --entrypoint python ito-linux-monitor-mcp \
  -m app.scan_known_hosts > "$tmp"

echo
cat "$tmp"
echo
read -r -p "Write these host keys to config/known_hosts? [y/N] " answer
if [[ "${answer}" =~ ^[Yy]$ ]]; then
  mv "$tmp" config/known_hosts
  chmod 644 config/known_hosts
  trap - EXIT
  echo "Wrote config/known_hosts"
  echo "IMPORTANT: verify fingerprints out-of-band on the target systems."
else
  echo "Not written."
fi
