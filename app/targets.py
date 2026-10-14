from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import yaml
from .config import TARGETS_FILE

@dataclass(frozen=True)
class Target:
    alias: str
    host: str
    user: str
    port: int
    connect_timeout: int
    command_timeout: int
    description: str
    tags: list[str]


def _positive_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def load_targets() -> dict[str, Target]:
    if not TARGETS_FILE.exists():
        raise RuntimeError(f"Targets file does not exist: {TARGETS_FILE}")
    data = yaml.safe_load(TARGETS_FILE.read_text(encoding="utf-8")) or {}
    defaults = data.get("defaults") or {}
    raw_targets = data.get("targets") or {}
    if not isinstance(raw_targets, dict):
        raise ValueError("'targets' must be a mapping")
    result: dict[str, Target] = {}
    for alias, raw in raw_targets.items():
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError("Target aliases must be non-empty strings")
        if not isinstance(raw, dict):
            raise ValueError(f"Target '{alias}' must be a mapping")
        host = str(raw.get("host", "")).strip()
        user = str(raw.get("user", defaults.get("user", ""))).strip()
        if not host:
            raise ValueError(f"Target '{alias}' is missing host")
        if not user:
            raise ValueError(f"Target '{alias}' is missing user")
        port = _positive_int(raw.get("port", defaults.get("port", 22)), "port", 1, 65535)
        connect_timeout = _positive_int(raw.get("connect_timeout", defaults.get("connect_timeout", 8)), "connect_timeout", 1, 60)
        command_timeout = _positive_int(raw.get("command_timeout", defaults.get("command_timeout", 20)), "command_timeout", 1, 300)
        description = str(raw.get("description", "")).strip()
        tags_raw = raw.get("tags") or []
        if not isinstance(tags_raw, list):
            raise ValueError(f"Target '{alias}' tags must be a list")
        result[alias] = Target(alias, host, user, port, connect_timeout, command_timeout, description, [str(t) for t in tags_raw])
    return result


def get_target(alias: str) -> Target:
    targets = load_targets()
    if alias not in targets:
        raise KeyError(f"Unknown target '{alias}'. Available targets: {', '.join(sorted(targets))}")
    return targets[alias]
