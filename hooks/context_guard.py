"""Pure telemetry helpers for the context guard hook."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _number(value: Any) -> int | float | None:
    """Return a finite number, excluding booleans and empty strings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def latest_primary_rate_limit(path: Path, tail_bytes: int = 262144) -> dict | None:
    """Find the newest usable five-hour primary snapshot in a JSONL tail."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - tail_bytes))
            data = stream.read()
    except (OSError, ValueError, TypeError):
        return None

    # A bounded read can begin in the middle of a JSONL record.  Discard that
    # partial record while retaining the final complete line if there is one.
    if size > len(data):
        _, separator, data = data.partition(b"\n")
        if not separator:
            return None

    for line in reversed(data.splitlines()):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "token_count":
            continue
        limits = event.get("rate_limits")
        if not isinstance(limits, dict):
            continue
        primary = limits.get("primary")
        if not isinstance(primary, dict):
            continue
        window = _number(primary.get("window_minutes"))
        used = _number(primary.get("used_percent"))
        resets_at = _number(primary.get("resets_at"))
        if window != 300 or used is None or resets_at is None:
            continue
        if not 0 <= used <= 100:
            continue
        snapshot = dict(primary)
        snapshot["window_minutes"] = window
        snapshot["used_percent"] = used
        snapshot["resets_at"] = resets_at
        return snapshot
    return None


def quota_warning(rate_limit: dict) -> str | None:
    """Classify remaining five-hour quota as no warning, soft, or strong."""
    if not isinstance(rate_limit, dict):
        return None
    if _number(rate_limit.get("window_minutes")) != 300:
        return None
    used = _number(rate_limit.get("used_percent"))
    if used is None or not 0 <= used <= 100:
        return None
    remaining = 100 - used
    if remaining > 25:
        return None
    if remaining > 15:
        return "soft"
    return "strong"
