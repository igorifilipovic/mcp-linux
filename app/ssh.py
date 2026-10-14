from __future__ import annotations

import socket
from typing import Any
import paramiko
from .config import KNOWN_HOSTS_FILE, MAX_OUTPUT_BYTES, SSH_KEY_FILE, SSH_KEY_PASSPHRASE_FILE, read_secret
from .targets import Target, get_target


def _truncate(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text, False
    clipped = encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return clipped + "\n[output truncated by MCP server]\n", True


def _connect(target: Target) -> paramiko.SSHClient:
    if not KNOWN_HOSTS_FILE.exists():
        raise RuntimeError(f"known_hosts file not found: {KNOWN_HOSTS_FILE}")
    if not SSH_KEY_FILE.exists():
        raise RuntimeError(f"SSH private key not found: {SSH_KEY_FILE}")
    passphrase = read_secret(SSH_KEY_PASSPHRASE_FILE, required=False) or None
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS_FILE))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=target.host,
        port=target.port,
        username=target.user,
        key_filename=str(SSH_KEY_FILE),
        passphrase=passphrase,
        timeout=target.connect_timeout,
        banner_timeout=target.connect_timeout,
        auth_timeout=target.connect_timeout,
        look_for_keys=False,
        allow_agent=False,
        compress=True,
    )
    return client


def execute(alias: str, command: str, timeout: int | None = None) -> dict[str, Any]:
    try:
        target = get_target(alias)
    except Exception as exc:
        return {"success": False, "target": alias, "error": str(exc)}
    client: paramiko.SSHClient | None = None
    try:
        client = _connect(target)
        cmd_timeout = timeout or target.command_timeout
        _stdin, stdout, stderr = client.exec_command(command, timeout=cmd_timeout, get_pty=False)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        out, out_truncated = _truncate(out)
        err, err_truncated = _truncate(err)
        return {
            "success": exit_code == 0,
            "target": alias,
            "host": target.host,
            "user": target.user,
            "exit_code": exit_code,
            "stdout": out,
            "stderr": err,
            "truncated": out_truncated or err_truncated,
        }
    except (socket.timeout, TimeoutError) as exc:
        return {"success": False, "target": alias, "host": target.host, "error": f"SSH timeout: {exc}"}
    except paramiko.BadHostKeyException as exc:
        return {"success": False, "target": alias, "host": target.host, "error": f"SSH host key mismatch: {exc}"}
    except paramiko.AuthenticationException as exc:
        return {"success": False, "target": alias, "host": target.host, "error": f"SSH authentication failed: {exc}"}
    except Exception as exc:
        return {"success": False, "target": alias, "host": target.host, "error": str(exc)}
    finally:
        if client is not None:
            client.close()
