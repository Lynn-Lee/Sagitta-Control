from __future__ import annotations

import re
from pathlib import Path


def normalize_engine_host(host: str) -> str:
    """
    When SagittaDB runs inside Docker, loopback addresses point to the
    container itself rather than the host machine. For local development we
    transparently rewrite localhost/127.0.0.1 to host.docker.internal so the
    backend container can reach host-mapped test databases.
    """
    normalized = host.strip()
    if normalized not in {"127.0.0.1", "localhost"}:
        return normalized
    if Path("/.dockerenv").exists():
        return "host.docker.internal"
    return normalized


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def sanitize_sqlglot_error(message: str) -> str:
    """Strip ANSI escapes from sqlglot error messages for user-facing display."""
    return ANSI_ESCAPE_RE.sub("", message)
