from __future__ import annotations

import socket
import sys

import paramiko

from .targets import load_targets


def host_field(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def main() -> None:
    targets = load_targets()
    failed = 0

    for alias, target in targets.items():
        sock = None
        transport = None
        try:
            sock = socket.create_connection((target.host, target.port), timeout=target.connect_timeout)
            transport = paramiko.Transport(sock)
            transport.start_client(timeout=target.connect_timeout)
            key = transport.get_remote_server_key()
            print(f"{host_field(target.host, target.port)} {key.get_name()} {key.get_base64()} # {alias}")
        except Exception as exc:
            failed += 1
            print(f"# ERROR {alias} {target.host}:{target.port}: {exc}", file=sys.stderr)
        finally:
            if transport is not None:
                transport.close()
            elif sock is not None:
                sock.close()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
