"""Fail-open Codex hook decisions for deliberate session handoffs."""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import sys
import time
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
    """Validate the newest non-null primary snapshot in a JSONL tail.

    An unusable newest snapshot fails open instead of reviving older telemetry.
    """
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
        if isinstance(event, dict) and event.get("type") == "event_msg":
            event = event.get("payload")
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
            return None
        if not 0 <= used <= 100:
            return None
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


ALLOW = {"decision": "allow"}


def _marker_path(data_dir: Path, session_id: str, resets_at: int | float, level: str) -> Path:
    """Create a filesystem-safe name for the documented marker key."""
    key = json.dumps([session_id, resets_at, level], separators=(",", ":"), ensure_ascii=True)
    return data_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".marker")


def _claim_marker(data_dir: Path, session_id: str, resets_at: int | float, level: str) -> bool:
    """Atomically claim a warning key, failing open if storage is unavailable."""
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        marker = _marker_path(data_dir, session_id, resets_at, level)
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _soft_reason() -> str:
    return "Five-hour quota is low. Consider $handoff-prepare before starting a fresh session."


def _strong_reason() -> str:
    return (
        "A fresh session is recommended. Run $handoff-prepare now; do not resume this "
        "same long-running session merely because the quota window resets."
    )


def handle_event(payload: dict, data_dir: Path) -> dict:
    """Return a Codex hook decision for prompt and compaction events.

    Telemetry and marker failures deliberately return allow.  ``data_dir`` is
    explicit for testability; the command entrypoint obtains its default from
    ``PLUGIN_DATA`` when Codex invokes the hook.
    """
    try:
        if not isinstance(payload, dict):
            return ALLOW
        if "agent_id" in payload:
            return ALLOW
        if payload.get("trigger") == "auto":
            return {"decision": "allow", "reason": _strong_reason()}
        if "trigger" in payload:
            return ALLOW

        session_id = payload.get("session_id")
        transcript_path = payload.get("transcript_path")
        if not isinstance(session_id, str) or not session_id or not isinstance(transcript_path, str):
            return ALLOW
        snapshot = latest_primary_rate_limit(Path(transcript_path))
        if snapshot is None:
            return ALLOW
        level = quota_warning(snapshot)
        if level is None:
            return ALLOW
        resets_at = _number(snapshot.get("resets_at"))
        if resets_at is None or resets_at <= time.time():
            return ALLOW
        if not _claim_marker(Path(data_dir), session_id, resets_at, level):
            return ALLOW
        if level == "soft":
            return {"decision": "allow", "reason": _soft_reason()}
        return {"decision": "block", "reason": _strong_reason()}
    except Exception:
        return ALLOW


def _plugin_data_dir() -> Path:
    """Use Codex-provided plugin storage, with a stable local fallback."""
    configured = os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured)
    return Path.home() / ".codex" / "plugin-data" / "codex-handoff"


def main() -> None:
    """Read one hook payload from stdin and emit the Codex decision JSON."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        payload = {}
    print(json.dumps(handle_event(payload, _plugin_data_dir()), separators=(",", ":")))


if __name__ == "__main__":
    main()
