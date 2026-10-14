from __future__ import annotations

import os
from pathlib import Path

TARGETS_FILE = Path(os.getenv("TARGETS_FILE", "/config/targets.yaml"))
KNOWN_HOSTS_FILE = Path(os.getenv("KNOWN_HOSTS_FILE", "/config/known_hosts"))
SSH_KEY_FILE = Path(os.getenv("SSH_KEY_FILE", "/run/secrets/monitor_ed25519"))
SSH_KEY_PASSPHRASE_FILE = Path(os.getenv("SSH_KEY_PASSPHRASE_FILE", "/run/secrets/monitor_ed25519.pass"))
MCP_BEARER_TOKEN_FILE = Path(os.getenv("MCP_BEARER_TOKEN_FILE", "/run/secrets/mcp_bearer_token"))
TLS_CERT_FILE = Path(os.getenv("TLS_CERT_FILE", "/run/tls/server.crt"))
TLS_KEY_FILE = Path(os.getenv("TLS_KEY_FILE", "/run/tls/server.key"))
MCP_PORT = int(os.getenv("MCP_PORT", "8443"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", str(1024 * 1024)))


def read_secret(path: Path, *, required: bool = True) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        if required:
            raise RuntimeError(f"Required secret file does not exist: {path}") from None
        return ""
    if required and not value:
        raise RuntimeError(f"Required secret file is empty: {path}")
    return value
