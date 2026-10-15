from __future__ import annotations

import re
import shlex
from typing import Literal

from mcp.server import MCPServer

from .ssh import execute
from .targets import get_target, load_targets

_SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]+$")
_SAFE_IFACE = re.compile(r"^[A-Za-z0-9_.:@-]+$")

mcp = MCPServer("ito-linux-monitor")


def _bounded(value: int, minimum: int, maximum: int, name: str) -> int:
    value = int(value)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@mcp.tool()
def list_targets() -> dict:
    """List configured Linux monitoring targets. No SSH connection is made."""
    targets = load_targets()
    return {
        "targets": [
            {
                "alias": t.alias,
                "host": t.host,
                "user": t.user,
                "port": t.port,
                "description": t.description,
                "tags": t.tags,
            }
            for t in targets.values()
        ]
    }


@mcp.tool()
def target_info(target: str) -> dict:
    """Show configuration metadata for one target without exposing secrets."""
    try:
        t = get_target(target)
        return {
            "success": True,
            "alias": t.alias,
            "host": t.host,
            "user": t.user,
            "port": t.port,
            "description": t.description,
            "tags": t.tags,
            "connect_timeout": t.connect_timeout,
            "command_timeout": t.command_timeout,
        }
    except Exception as exc:
        return {"success": False, "target": target, "error": str(exc)}


@mcp.tool()
def ssh_check(target: str) -> dict:
    """Verify SSH access and report the remote identity and hostname."""
    return execute(target, "printf 'ssh_ok\\n'; id -un; hostname; id")


@mcp.tool()
def system_snapshot(target: str) -> dict:
    """Return a broad read-only system snapshot using only ordinary-user commands."""
    command = r"""printf '%s\n' '=== timestamp ==='; date -Is 2>&1 || date
printf '%s\n' '=== identity ==='; hostname; id; uname -a
printf '%s\n' '=== os ==='; cat /etc/os-release 2>/dev/null || true
printf '%s\n' '=== uptime/load ==='; uptime; cat /proc/loadavg 2>/dev/null || true
printf '%s\n' '=== cpu ==='; nproc 2>/dev/null || true; lscpu 2>/dev/null | sed -n '1,20p' || true
printf '%s\n' '=== memory/swap ==='; free -h 2>/dev/null || true; cat /proc/swaps 2>/dev/null || true
printf '%s\n' '=== filesystems ==='; df -hPT 2>/dev/null || df -h
printf '%s\n' '=== failed units ==='; systemctl --failed --no-pager 2>&1 || true
printf '%s\n' '=== pressure ==='; for f in /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io; do [ -r "$f" ] && { echo "-- $f"; cat "$f"; }; done
"""
    return execute(target, command, timeout=45)


@mcp.tool()
def disk_capacity(target: str) -> dict:
    """Show filesystem capacity, inode usage, mounts and block-device layout."""
    command = r"""printf '%s\n' '=== capacity ==='; df -hPT 2>&1
printf '%s\n' '=== inodes ==='; df -hiP 2>&1
printf '%s\n' '=== block devices ==='; lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,ROTA,RO 2>&1 || true
printf '%s\n' '=== mounts ==='; findmnt -r -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1 || true
"""
    return execute(target, command)


@mcp.tool()
def disk_io(target: str, samples: int = 2, interval_seconds: int = 1) -> dict:
    """Show disk I/O load. Uses iostat when available, otherwise /proc/diskstats and PSI."""
    samples = _bounded(samples, 2, 10, "samples")
    interval_seconds = _bounded(interval_seconds, 1, 10, "interval_seconds")
    command = f"""printf '%s\\n' '=== disk io ==='
if command -v iostat >/dev/null 2>&1; then
  iostat -dx {interval_seconds} {samples}
else
  echo 'iostat not installed; returning /proc/diskstats counters instead'
  cat /proc/diskstats
fi
printf '%s\\n' '=== io pressure ==='
[ -r /proc/pressure/io ] && cat /proc/pressure/io || true
"""
    return execute(target, command, timeout=(interval_seconds * samples + 15))


@mcp.tool()
def cpu_status(target: str) -> dict:
    """Show CPU topology, load, utilization snapshot and CPU pressure."""
    command = r"""printf '%s\n' '=== load ==='; uptime; cat /proc/loadavg 2>/dev/null || true
printf '%s\n' '=== cpu count/topology ==='; nproc 2>/dev/null || true; lscpu 2>&1 | sed -n '1,35p'
printf '%s\n' '=== utilization snapshot ==='; top -bn1 2>&1 | head -20
printf '%s\n' '=== cpu pressure ==='; [ -r /proc/pressure/cpu ] && cat /proc/pressure/cpu || true
"""
    return execute(target, command)


@mcp.tool()
def memory_swap(target: str) -> dict:
    """Show RAM and swap consumption plus memory-pressure information."""
    command = r"""printf '%s\n' '=== free ==='; free -h 2>&1
printf '%s\n' '=== swap ==='; cat /proc/swaps 2>&1 || true
printf '%s\n' '=== selected meminfo ==='; grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapCached|SwapTotal|SwapFree|Dirty|Writeback|Slab|SReclaimable|Shmem):' /proc/meminfo 2>&1 || true
printf '%s\n' '=== memory pressure ==='; [ -r /proc/pressure/memory ] && cat /proc/pressure/memory || true
"""
    return execute(target, command)


@mcp.tool()
def network_overview(target: str) -> dict:
    """Show interfaces, addresses, routes, counters and socket summary without privileged operations."""
    command = r"""printf '%s\n' '=== addresses ==='; ip -br addr 2>&1
printf '%s\n' '=== routes ==='; ip route 2>&1
printf '%s\n' '=== link counters ==='; ip -s link 2>&1
printf '%s\n' '=== socket summary ==='; ss -s 2>&1
printf '%s\n' '=== resolvers ==='; cat /etc/resolv.conf 2>/dev/null || true
"""
    return execute(target, command)


@mcp.tool()
def network_interface(target: str, interface: str) -> dict:
    """Show detailed counters and configuration for one network interface."""
    if not _SAFE_IFACE.fullmatch(interface):
        return {"success": False, "error": "Invalid interface name"}
    iface = shlex.quote(interface)
    return execute(target, f"ip addr show dev {iface}; printf '\\n=== counters ===\\n'; ip -s link show dev {iface}")


@mcp.tool()
def network_sockets(target: str, limit: int = 200) -> dict:
    """List TCP/UDP sockets visible to the ordinary monitoring user."""
    limit = _bounded(limit, 10, 500, "limit")
    return execute(target, f"ss -tun 2>&1 | head -n {limit + 1}")


@mcp.tool()
def performance_snapshot(target: str, interval_seconds: int = 1) -> dict:
    """Collect short CPU, run-queue, memory, paging, disk-I/O and pressure snapshots."""
    interval_seconds = _bounded(interval_seconds, 1, 10, "interval_seconds")
    command = f"""printf '%s\\n' '=== vmstat ==='; vmstat {interval_seconds} 2 2>&1 || true
printf '%s\\n' '=== iostat ==='; if command -v iostat >/dev/null 2>&1; then iostat -dx {interval_seconds} 2; else echo 'iostat not installed'; fi
printf '%s\\n' '=== pressure ==='; for f in /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io; do [ -r "$f" ] && {{ echo "-- $f"; cat "$f"; }}; done
"""
    return execute(target, command, timeout=(interval_seconds * 4 + 15))


@mcp.tool()
def processes(target: str, sort_by: Literal["cpu", "memory"] = "cpu", limit: int = 30) -> dict:
    """Show the most CPU- or memory-consuming processes visible to the monitoring user."""
    limit = _bounded(limit, 5, 200, "limit")
    sort_field = "-%cpu" if sort_by == "cpu" else "-%mem"
    command = (
        "ps -eo pid,ppid,user,stat,ni,pri,%cpu,%mem,rss,vsz,etime,comm,args "
        f"--sort={sort_field} | head -n {limit + 1}"
    )
    return execute(target, command)


@mcp.tool()
def service_status(target: str, service: str) -> dict:
    """Read systemd service status. This never starts, stops or restarts a service."""
    if not _SAFE_UNIT.fullmatch(service):
        return {"success": False, "error": "Invalid systemd unit name"}
    return execute(target, f"systemctl status --no-pager --full {shlex.quote(service)} 2>&1")


@mcp.tool()
def failed_services(target: str) -> dict:
    """List failed systemd units visible to the ordinary user."""
    return execute(target, "systemctl --failed --no-pager --full 2>&1")


@mcp.tool()
def journal_logs(
    target: str,
    scope: Literal["system", "user"] = "system",
    service: str = "",
    lines: int = 100,
    since_minutes: int = 60,
) -> dict:
    """Read journal entries accessible to the monitoring user. No sudo is used."""
    lines = _bounded(lines, 10, 500, "lines")
    since_minutes = _bounded(since_minutes, 1, 10080, "since_minutes")
    parts = ["journalctl"]
    if scope == "user":
        parts.append("--user")
    parts.extend(["--no-pager", "--output=short-iso", "-n", str(lines), "--since", shlex.quote(f"-{since_minutes} minutes")])
    if service:
        if not _SAFE_UNIT.fullmatch(service):
            return {"success": False, "error": "Invalid systemd unit name"}
        parts.extend(["-u", shlex.quote(service)])
    return execute(target, " ".join(parts) + " 2>&1", timeout=30)


def _tail_stdout(result: dict, lines: int) -> dict:
    """Trim stdout to the last N lines without adding any remote shell pipeline."""
    if not isinstance(result, dict) or "stdout" not in result:
        return result

    stdout = result.get("stdout") or ""
    split = stdout.splitlines()
    if len(split) > lines:
        result = dict(result)
        result["stdout"] = "\n".join(split[-lines:]) + "\n"
        result["output_filtered_by_mcp"] = True
        result["returned_lines"] = lines
    return result


@mcp.tool()
def kernel_messages(target: str, lines: int = 100) -> dict:
    """Read recent kernel messages via one exact sudo-approved dmesg command.

    Target sudoers must allow exactly:
      /usr/bin/dmesg --color=never

    The line limit is applied inside the MCP after the command returns; it is
    never interpolated into the privileged command.
    """
    lines = _bounded(lines, 10, 500, "lines")
    result = execute(target, "sudo -n /usr/bin/dmesg --color=never")
    return _tail_stdout(result, lines)


@mcp.tool()
def docker_ps(target: str, include_stopped: bool = False) -> dict:
    """List Docker containers via an exact sudo allowlist.

    The caller cannot supply Docker CLI arguments. The MCP chooses only between
    these two fixed commands:
      /usr/bin/docker ps
      /usr/bin/docker ps -a
    """
    command = (
        "sudo -n /usr/bin/docker ps -a"
        if include_stopped
        else "sudo -n /usr/bin/docker ps"
    )
    return execute(target, command)


@mcp.tool()
def hardware_sensors(target: str) -> dict:
    """Show temperature/sensor information available without privileges."""
    command = r"""if command -v sensors >/dev/null 2>&1; then
  sensors 2>&1
else
  echo 'lm-sensors command not installed'
fi
printf '%s\n' '=== thermal sysfs ==='
for z in /sys/class/thermal/thermal_zone*; do
  [ -d "$z" ] || continue
  printf '%s ' "$z"
  cat "$z/type" 2>/dev/null | tr '\n' ' '
  cat "$z/temp" 2>/dev/null || true
done
"""
    return execute(target, command)
