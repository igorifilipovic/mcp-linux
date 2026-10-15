# Changelog

## 2.0.0

- Added `docker_ps(target, include_stopped=False)`.
- Docker monitoring is limited to the exact privileged commands `docker ps` and `docker ps -a`.
- Changed `kernel_messages` to use the exact privileged command `dmesg --color=never` and trim lines inside the MCP instead of using a privileged shell pipeline.
- Added `target-setup/ito-linux-monitor.sudoers.example` with the narrow sudo allowlist.
- The `ito-linux-monitor` account remains outside the Docker group and has no arbitrary sudo access.
- Health endpoint now reports version `2.0.0`.
