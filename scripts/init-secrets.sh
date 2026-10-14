#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="${ROOT}/secrets"
TLS="${SECRETS}/tls"

CN="${1:-ito-linux-monitor.local}"
SAN="${2:-DNS:${CN}}"

mkdir -p "${TLS}" "${ROOT}/config"
umask 077

if [[ ! -f "${SECRETS}/mcp_bearer_token" ]]; then
  openssl rand -hex 32 > "${SECRETS}/mcp_bearer_token"
  echo "Created bearer token: ${SECRETS}/mcp_bearer_token"
else
  echo "Bearer token already exists; leaving it unchanged."
fi

if [[ ! -f "${SECRETS}/monitor_ed25519" ]]; then
  echo
  echo "Creating dedicated Ed25519 monitoring key."
  echo "You may enter a passphrase, or press Enter for none."
  ssh-keygen -t ed25519 -a 100 -f "${SECRETS}/monitor_ed25519"
  echo
  echo "If you used a passphrase, enter the SAME passphrase once more for the MCP secret file."
  echo "If the key has no passphrase, press Enter."
  while true; do
    read -rsp "SSH key passphrase: " PASSPHRASE
    echo
    if ssh-keygen -y -P "${PASSPHRASE}" -f "${SECRETS}/monitor_ed25519" >/dev/null 2>&1; then
      printf '%s' "${PASSPHRASE}" > "${SECRETS}/monitor_ed25519.pass"
      unset PASSPHRASE
      break
    fi
    echo "Passphrase does not unlock the key; try again." >&2
  done
else
  echo "SSH key already exists; leaving it unchanged."
  [[ -f "${SECRETS}/monitor_ed25519.pass" ]] || : > "${SECRETS}/monitor_ed25519.pass"
fi

if [[ ! -f "${TLS}/server.crt" || ! -f "${TLS}/server.key" ]]; then
  echo "Creating self-signed TLS certificate: CN=${CN}, SAN=${SAN}"
  openssl req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes \
    -keyout "${TLS}/server.key" \
    -out "${TLS}/server.crt" \
    -subj "/CN=${CN}" \
    -addext "subjectAltName=${SAN}"
else
  echo "TLS certificate already exists; leaving it unchanged."
fi

chmod 600 \
  "${SECRETS}/mcp_bearer_token" \
  "${SECRETS}/monitor_ed25519" \
  "${SECRETS}/monitor_ed25519.pass" \
  "${TLS}/server.key"
chmod 644 "${SECRETS}/monitor_ed25519.pub" "${TLS}/server.crt"

echo
echo "Secrets created. Before starting Docker, make the private files readable"
echo "by container UID 10001 (root can always override this):"
echo
echo "  sudo chown 10001:10001 ${SECRETS}/mcp_bearer_token ${SECRETS}/monitor_ed25519 ${SECRETS}/monitor_ed25519.pass ${TLS}/server.key"
echo "  sudo chmod 400 ${SECRETS}/mcp_bearer_token ${SECRETS}/monitor_ed25519 ${SECRETS}/monitor_ed25519.pass ${TLS}/server.key"
