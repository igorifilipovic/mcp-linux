# ITO Linux Monitor MCP v2

Read-only Linux monitoring MCP server designed for remote observability over SSH. It is pinned to the current MCP Python SDK v2.3.0 line.

The server runs in Docker, exposes **Streamable HTTP over HTTPS**, and rejects MCP requests unless the caller sends the configured **Bearer token**. Most target commands run as the unprivileged `ito-linux-monitor` user. Version 2 adds only three narrowly scoped `sudo` command lines for information that is commonly unavailable to an ordinary user: `docker ps`, `docker ps -a`, and `dmesg --color=never`. There is still **no arbitrary command tool, no general sudo, no service restart, no reboot and no file-write tool**.

## Architecture

```text
MCP client
   |
   | HTTPS :8443
   | Authorization: Bearer <token>
   v
ito-linux-monitor-mcp container
   |
   | Paramiko SSH
   | dedicated private key
   | strict known_hosts verification
   v
Linux targets
   user: ito-linux-monitor
   ordinary monitoring commands
   + exact sudo allowlist only for:
       docker ps
       docker ps -a
       dmesg --color=never
```

## Security model

- Container process runs as UID/GID `10001:10001`, not root.
- Container filesystem is read-only; only `/tmp` is writable tmpfs.
- All Linux capabilities are dropped and `no-new-privileges` is enabled.
- HTTPS terminates directly in the MCP process through Uvicorn TLS.
- `/mcp` requires an exact static Bearer token; `/health` is the only unauthenticated path.
- Bearer token is read from a mounted file, not from the Docker environment.
- SSH private key is mounted read-only only into this service.
- SSH agent discovery and `~/.ssh` key discovery are disabled.
- SSH server host keys must already exist in `config/known_hosts`; unknown keys are rejected.
- There is no general-purpose `run_command` MCP tool.
- Most target operations run without `sudo`.
- The only privileged tool paths in v2 are hard-coded to `docker ps`, `docker ps -a`, and `dmesg --color=never`; callers cannot provide extra Docker or dmesg arguments.
- The target user must **not** be added to the `docker` group and must not receive general-purpose sudo rights.

**Important:** root on the Docker host (and a user with unrestricted Docker-daemon access) can ultimately access bind-mounted secrets. Linux permissions can prevent normal host users and other containers from reading the key, but they cannot protect a secret from host root.

## MCP tools

| Tool | Purpose |
|---|---|
| `list_targets` | List configured target aliases and metadata |
| `target_info` | Show one target's address/user/metadata |
| `ssh_check` | Verify SSH identity and connectivity |
| `system_snapshot` | Broad snapshot: OS, kernel, uptime, load, CPU, RAM, swap, disks, failed units, PSI |
| `disk_capacity` | Filesystem capacity, inode usage, mounts and block-device layout |
| `disk_io` | Disk I/O load via `iostat`; fallback to `/proc/diskstats`; includes I/O PSI |
| `cpu_status` | CPU topology, load, `top` snapshot and CPU pressure |
| `memory_swap` | RAM, swap, selected `/proc/meminfo`, memory pressure |
| `network_overview` | Interfaces, addresses, routes, counters, socket summary, resolver config |
| `network_interface` | Detailed state/counters for one validated interface name |
| `network_sockets` | TCP/UDP sockets visible to the monitoring user |
| `performance_snapshot` | `vmstat`, optional `iostat`, CPU/memory/I/O pressure |
| `processes` | Top CPU or memory processes |
| `service_status` | Read-only `systemctl status` |
| `failed_services` | Failed systemd units |
| `journal_logs` | Journal entries the ordinary user is permitted to read |
| `kernel_messages` | Recent kernel messages via the exact sudo-approved `/usr/bin/dmesg --color=never` command |
| `docker_ps` | Running containers (`docker ps`) or all containers (`docker ps -a`) via exact sudo-approved commands |
| `hardware_sensors` | `sensors` if installed plus readable thermal sysfs values |

### Expected ordinary-user limitations

The server intentionally does not bypass OS permissions. Depending on the target's distro/hardening:

- `journalctl` may show only the monitoring user's journal or a limited system journal.
- `kernel_messages` requires the v2 sudoers rule; without it the command is rejected by `sudo -n`.
- `docker_ps` requires Docker plus the v2 sudoers rules; the monitoring user is intentionally **not** placed in the `docker` group.
- process details for other users may be restricted by `/proc` mount options.
- some socket/process ownership fields are hidden from non-root users.
- `iostat` requires the `sysstat` package to be installed, but does **not** require root to run.
- `sensors` requires `lm-sensors` if you want that part of the output.

Those restrictions are treated as normal results, not a reason to grant sudo.

---

# 1. Prepare the project

```bash
cp .env.example .env
cp config/targets.yaml.example config/targets.yaml
```

Edit `config/targets.yaml`:

```yaml
defaults:
  user: ito-linux-monitor
  port: 22
  connect_timeout: 8
  command_timeout: 20

targets:
  app01:
    host: 192.168.1.21
    description: Application server
    tags: [linux, app]

  db01:
    host: 192.168.1.22
    description: Database server
    tags: [linux, database]
```

The file is re-read for each tool call, so adding/removing targets does not require an MCP restart. A new target does still need its SSH host key added to `known_hosts`.

# 2. Create MCP secrets, SSH key and TLS certificate

For a self-signed certificate:

```bash
./scripts/init-secrets.sh ito-linux-monitor.local \
  'DNS:ito-linux-monitor.local,IP:192.168.1.50'
```

The script creates:

```text
secrets/mcp_bearer_token
secrets/monitor_ed25519
secrets/monitor_ed25519.pub
secrets/monitor_ed25519.pass
secrets/tls/server.crt
secrets/tls/server.key
```

You may replace `server.crt` and `server.key` with certificates from your internal CA or a public CA.

The SSH key can be passphrase-protected. The passphrase is stored separately in `monitor_ed25519.pass`; only the MCP container mounts both files.

Before starting the container, make the sensitive files readable only by the runtime UID (`10001`) and root:

```bash
sudo chown 10001:10001 \
  secrets/mcp_bearer_token \
  secrets/monitor_ed25519 \
  secrets/monitor_ed25519.pass \
  secrets/tls/server.key

sudo chmod 400 \
  secrets/mcp_bearer_token \
  secrets/monitor_ed25519 \
  secrets/monitor_ed25519.pass \
  secrets/tls/server.key
```

The public key and certificate can remain `0644`.

To display the bearer token later:

```bash
./scripts/show-bearer-token.sh
```

# 3. Create the target-side monitoring user

This is a **one-time provisioning step** performed by an administrator on each target. The MCP receives no general root shell or general-purpose sudo access.

Example on a target:

```bash
sudo useradd --create-home --shell /bin/bash ito-linux-monitor
sudo install -d -m 700 -o ito-linux-monitor -g ito-linux-monitor \
  /home/ito-linux-monitor/.ssh
```

On the MCP host, print the restricted public-key line:

```bash
./scripts/print-authorized-key.sh
```

It prints a line beginning with:

```text
restrict ssh-ed25519 ...
```

Append that complete line to the target's:

```text
/home/ito-linux-monitor/.ssh/authorized_keys
```

Then:

```bash
sudo chown ito-linux-monitor:ito-linux-monitor \
  /home/ito-linux-monitor/.ssh/authorized_keys
sudo chmod 600 /home/ito-linux-monitor/.ssh/authorized_keys
```

Do **not** add `ito-linux-monitor` to the `docker` group.

For even tighter SSH exposure, you may prepend a source IP restriction to the key, for example:

```text
from="192.168.1.50",restrict ssh-ed25519 AAAA...
```

where `192.168.1.50` is the MCP server's source IP as seen by the target.

## 3.1 Add the v2 exact sudo allowlist

First verify the actual binary paths on the target:

```bash
command -v docker
command -v dmesg
```

The supplied template assumes:

```text
/usr/bin/docker
/usr/bin/dmesg
```

Open a dedicated sudoers file:

```bash
sudo visudo -f /etc/sudoers.d/ito-linux-monitor
```

and add:

```sudoers
Cmnd_Alias ITO_LINUX_MONITOR_READONLY = /usr/bin/docker ps, /usr/bin/docker ps -a, /usr/bin/dmesg --color=never
ito-linux-monitor ALL=(root) NOPASSWD: ITO_LINUX_MONITOR_READONLY
```

The same text is included as:

```text
target-setup/ito-linux-monitor.sudoers.example
```

If `command -v` reports different paths, use those exact paths in both sudoers and `app/tools.py`. Do not use wildcards such as `/usr/bin/docker *`. On targets that do not run Docker, simply omit the two Docker entries and keep only the dmesg rule.

Validate the resulting policy:

```bash
sudo visudo -c
sudo -l -U ito-linux-monitor
```

Then test as the monitoring user:

```bash
sudo -u ito-linux-monitor sudo -n /usr/bin/docker ps
sudo -u ito-linux-monitor sudo -n /usr/bin/docker ps -a
sudo -u ito-linux-monitor sudo -n /usr/bin/dmesg --color=never | head
```

These examples must be rejected:

```bash
sudo -u ito-linux-monitor sudo -n /usr/bin/docker inspect anything
sudo -u ito-linux-monitor sudo -n /usr/bin/docker run --rm alpine id
sudo -u ito-linux-monitor sudo -n /bin/bash
```

# 4. Build and capture target SSH host keys

Build first:

```bash
docker compose build
```

Then:

```bash
./scripts/scan-known-hosts.sh
```

The script retrieves the presented SSH server keys for every target in `targets.yaml` and offers to save them to:

```text
config/known_hosts
```

**Do not treat first-contact scanning as identity proof.** Verify the fingerprints out-of-band against the target systems before accepting them. Strict host-key verification prevents silent host substitution only after you have established a trusted key.

# 5. Start the MCP server

```bash
docker compose up -d
```

Check:

```bash
docker compose ps
docker compose logs --tail=100 ito-linux-monitor-mcp
```

The endpoint is:

```text
https://MCP_HOST:8443/mcp
```

Health:

```text
https://MCP_HOST:8443/health
```

Quick edge test with the self-signed certificate:

```bash
./scripts/test-endpoint.sh 127.0.0.1 8443
```

Expected:

```text
Health: 200
MCP without token: 401
```

# 6. Client authentication

Every MCP HTTP request must include:

```http
Authorization: Bearer <your-token>
```

Use the token from:

```text
secrets/mcp_bearer_token
```

For a self-signed TLS certificate, the client must either trust that certificate/CA or explicitly disable certificate verification for the initial lab test. For normal operation, trusting an internal CA is preferred over disabling TLS verification.

A generic client definition conceptually looks like:

```yaml
linux-monitor:
  url: https://ito-linux-monitor.example.lan:8443/mcp
  headers:
    Authorization: Bearer <token>
```

The exact header syntax depends on the MCP client you use.

# 7. Test SSH from the MCP client

Start with:

```text
list_targets
ssh_check(target="app01")
system_snapshot(target="app01")
```

Then try focused tools such as:

```text
disk_capacity(target="app01")
disk_io(target="app01", samples=2, interval_seconds=1)
network_overview(target="app01")
cpu_status(target="app01")
memory_swap(target="app01")
processes(target="app01", sort_by="cpu", limit=30)
journal_logs(target="app01", lines=100, since_minutes=60)
kernel_messages(target="app01", lines=100)
docker_ps(target="app01")
docker_ps(target="app01", include_stopped=true)
```

# 8. Adding another target

1. Create the `ito-linux-monitor` account on the new target.
2. Add the restricted public key to that account's `authorized_keys`.
3. Add one YAML entry to `config/targets.yaml`.
4. Regenerate/review `config/known_hosts` (preserve existing trusted entries).
5. Call `list_targets` / `ssh_check`.

The MCP server re-reads `targets.yaml` on each call, so target inventory changes are immediate.

# Design choices

## Why no arbitrary command tool?

The purpose of this server is monitoring. A generic shell tool would turn an otherwise read-only monitoring service into a remote administration surface. This implementation exposes fixed diagnostic operations and validates the small number of arguments that become part of shell commands. The v2 Docker and dmesg tools also use fixed command lines; the requester cannot append arbitrary privileged arguments.

## Why limited sudo instead of the Docker group?

Membership in the rootful Docker daemon's `docker` group is effectively a high-privilege capability. Version 2 deliberately avoids that. The monitoring account receives only three exact NOPASSWD command lines through sudoers. This is much narrower than general Docker access and much simpler operationally than installing a separate socket proxy on every target.

## Why strict `known_hosts`?

The previous general-purpose Linux MCP used automatic host-key acceptance. This monitoring server rejects unknown or changed SSH server keys so an intercepted SSH connection is not silently trusted.

## Why a static Bearer token?

A single static token is simple for a private service-to-service deployment. If you later need multiple callers, per-client revocation, identity, scopes, audit attribution or expiry, replace the static token middleware with JWT/OAuth 2.1 validation.

## Why direct TLS instead of a reverse proxy?

For this standalone service, direct Uvicorn TLS keeps deployment to one container and ensures there is no clear-text hop between a TLS proxy and the MCP application. A reverse proxy is still reasonable later if you centralize certificates or ingress.

# Git

Real configuration and secrets are ignored by `.gitignore`. Commit only examples and code:

```text
config/targets.yaml.example
.env.example
Dockerfile
compose.yaml
app/
scripts/
target-setup/ito-linux-monitor.sudoers.example
VERSION
CHANGELOG.md
README.md
```

Do not commit:

```text
.env
config/targets.yaml
config/known_hosts
secrets/*
```
