"""Fail-open Codex hook decisions for deliberate session handoffs."""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
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


def _latest_rate_limit(path: Path, key: str, window_minutes: int, tail_bytes: int = 262144) -> dict | None:
    """Validate the newest non-null named rate-limit snapshot in a JSONL tail.

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
        rate_limit = limits.get(key)
        if not isinstance(rate_limit, dict):
            continue
        window = _number(rate_limit.get("window_minutes"))
        used = _number(rate_limit.get("used_percent"))
        resets_at = _number(rate_limit.get("resets_at"))
        if window != window_minutes or used is None or resets_at is None:
            return None
        if not 0 <= used <= 100:
            return None
        snapshot = dict(rate_limit)
        snapshot["window_minutes"] = window
        snapshot["used_percent"] = used
        snapshot["resets_at"] = resets_at
        return snapshot
    return None


def latest_primary_rate_limit(path: Path, tail_bytes: int = 262144) -> dict | None:
    """Return the newest valid five-hour quota snapshot."""
    return _latest_rate_limit(path, "primary", 300, tail_bytes)


def latest_secondary_rate_limit(path: Path, tail_bytes: int = 262144) -> dict | None:
    """Return the newest valid weekly quota snapshot."""
    return _latest_rate_limit(path, "secondary", 10080, tail_bytes)


def quota_warning(rate_limit: dict, window_minutes: int = 300, soft_warning: bool = True) -> str | None:
    """Classify remaining quota as no warning, soft, or strong."""
    if not isinstance(rate_limit, dict):
        return None
    if _number(rate_limit.get("window_minutes")) != window_minutes:
        return None
    used = _number(rate_limit.get("used_percent"))
    if used is None or not 0 <= used <= 100:
        return None
    remaining = 100 - used
    if remaining > 15 or (not soft_warning and remaining > 6):
        return None
    if remaining > 6:
        return "soft"
    return "strong"


ALLOW = {"decision": "allow"}


def _marker_path(data_dir: Path, *key_parts: object) -> Path:
    """Create a filesystem-safe name for a marker key."""
    key = json.dumps(list(key_parts), separators=(",", ":"), ensure_ascii=True)
    return data_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".marker")


def _claim_marker(data_dir: Path, *key_parts: object) -> bool:
    """Atomically claim a marker key, failing open if storage is unavailable."""
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        marker = _marker_path(data_dir, *key_parts)
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _marker_exists(data_dir: Path, *key_parts: object) -> bool:
    """Test a marker key, failing open if storage is unavailable."""
    try:
        return _marker_path(data_dir, *key_parts).is_file()
    except (OSError, TypeError, ValueError):
        return False


def _pending_choice_exists(
    data_dir: Path, session_id: str, resets_at: int | float, window: str
) -> bool:
    """Return whether this still-active quota window awaits the user's choice."""
    return _marker_exists(data_dir, session_id, resets_at, "pending-choice", window)


def _claim_pending_choice(
    data_dir: Path, session_id: str, resets_at: int | float, window: str
) -> bool:
    """Record the minimal choice state without retaining any prompt content."""
    return _claim_marker(data_dir, session_id, resets_at, "pending-choice", window)


def _clear_pending_choice(
    data_dir: Path, session_id: str, resets_at: int | float, window: str
) -> None:
    """Consume a choice marker, failing open when local storage is unavailable."""
    try:
        _marker_path(data_dir, session_id, resets_at, "pending-choice", window).unlink(missing_ok=True)
    except (OSError, TypeError, ValueError):
        pass


def _turn_latch_dir(data_dir: Path, session_id: str, turn_id: str) -> Path:
    """Group full-key latches for lookup without rereading quota telemetry."""
    return _marker_path(data_dir, session_id, turn_id, "tool-stop").with_suffix(".latches")


def claim_turn_latch(
    data_dir: Path, session_id: str, turn_id: str, resets_at: int | float, window: str
) -> bool:
    """Atomically claim the documented same-turn tool-stop latch."""
    if not isinstance(session_id, str) or not session_id:
        return False
    if not isinstance(turn_id, str) or not turn_id:
        return False
    if _number(resets_at) is None or not isinstance(window, str) or not window:
        return False
    return _claim_marker(
        _turn_latch_dir(data_dir, session_id, turn_id),
        session_id, turn_id, resets_at, "tool-stop", window,
    )


def turn_latch_exists(
    data_dir: Path, session_id: str, turn_id: str, resets_at: int | float, window: str
) -> bool:
    """Return whether the documented same-turn tool-stop latch exists."""
    if not isinstance(session_id, str) or not session_id:
        return False
    if not isinstance(turn_id, str) or not turn_id:
        return False
    if _number(resets_at) is None or not isinstance(window, str) or not window:
        return False
    return _marker_exists(
        _turn_latch_dir(data_dir, session_id, turn_id),
        session_id, turn_id, resets_at, "tool-stop", window,
    )


def claim_strong_tool_stop(
    data_dir: Path, session_id: str, turn_id: str, resets_at: int | float, window: str
) -> bool:
    """Claim one strong warning and latch only the turn that claimed it."""
    if not _claim_marker(data_dir, session_id, resets_at, "strong", window):
        return False
    if not claim_turn_latch(data_dir, session_id, turn_id, resets_at, window):
        return False
    _claim_pending_choice(data_dir, session_id, resets_at, window)
    return True


def _soft_reason() -> str:
    return "Five-hour quota is low. Consider $handoff-prepare before starting a fresh session."


def _strong_reason() -> str:
    return (
        "A fresh session is recommended. Run $handoff-prepare now; do not resume this "
        "same long-running session merely because the quota window resets."
    )


def _weekly_strong_reason() -> str:
    return "Weekly quota is nearly exhausted. Run $handoff-prepare before continuing in a fresh session."


def _choice_reason(reasons: list[str]) -> str:
    """Describe the only two user-controlled responses after a strong stop."""
    prefix = " ".join(reasons)
    if prefix:
        prefix += " "
    return (
        prefix
        + "This work is paused because the quota is nearly exhausted. Reply "
        "`$codex-handoff:handoff-prepare` (or `$handoff-prepare`) to save a checkpoint, "
        "or reply `continue` to resume the paused work."
    )


def _tool_stop_reason(reasons: list[str]) -> str:
    """Describe a non-blocking stop advisory after a completed local tool."""
    return _choice_reason(reasons + [
        "The completed tool result is preserved. Stop expanding work and summarize the current state."
    ])


HANDOFF_COMMAND_RE = re.compile(
    r"(?<![\w-]|\$)\$?(?:codex-handoff:)?handoff-prepare\b",
    re.IGNORECASE,
)


def is_handoff_command(prompt: object) -> bool:
    """Check if the user prompt is invoking handoff-prepare."""
    if not isinstance(prompt, str):
        return False
    return bool(HANDOFF_COMMAND_RE.search(prompt))


def is_continue_command(prompt: object) -> bool:
    """Check if the user prompt is requesting to continue development."""
    if not isinstance(prompt, str):
        return False
    return prompt.strip().lower() == "continue"


def handle_user_prompt(payload: dict, data_dir: Path) -> dict:
    """Return the V1 quota decision for a user-prompt event."""
    try:
        if not isinstance(payload, dict):
            return ALLOW
        if "agent_id" in payload:
            return ALLOW
        session_id = payload.get("session_id")
        transcript_path = payload.get("transcript_path")
        if not isinstance(session_id, str) or not session_id or not isinstance(transcript_path, str):
            return ALLOW
        primary = latest_primary_rate_limit(Path(transcript_path))
        secondary = latest_secondary_rate_limit(Path(transcript_path))
        strong_windows = []
        for window, snapshot, level, reason in (
            ("five-hour", primary, quota_warning(primary) if primary else None, _strong_reason()),
            ("weekly", secondary,
             quota_warning(secondary, window_minutes=10080, soft_warning=False) if secondary else None,
             _weekly_strong_reason()),
        ):
            if level != "strong":
                continue
            resets_at = _number(snapshot.get("resets_at"))
            if resets_at is not None and resets_at > time.time():
                strong_windows.append((window, resets_at, reason))

        prompt = payload.get("prompt")

        # 1. Handoff command is a safe exit: clear pending choices, claim strong, and allow immediately
        if is_handoff_command(prompt):
            for window, resets_at, _ in strong_windows:
                _clear_pending_choice(Path(data_dir), session_id, resets_at, window)
                _claim_marker(Path(data_dir), session_id, resets_at, "strong", window)
            return ALLOW

        active_resets = [
            r for r in (_number(s.get("resets_at")) if s else None for s in (primary, secondary))
            if r is not None and r > time.time()
        ]

        # 2. If user already chose to continue in this session, do not block or warn again
        if any(_marker_exists(Path(data_dir), session_id, r, "user-continue") for r in active_resets):
            return ALLOW

        # 3. Check for pending choices from a previous block
        pending = [
            (window, resets_at) for window, resets_at, _ in strong_windows
            if _pending_choice_exists(Path(data_dir), session_id, resets_at, window)
        ]
        if pending:
            if is_continue_command(prompt):
                for window, resets_at in pending:
                    _clear_pending_choice(Path(data_dir), session_id, resets_at, window)
                for r in active_resets:
                    _claim_marker(Path(data_dir), session_id, r, "user-continue")
                for window, resets_at, _ in strong_windows:
                    _claim_marker(Path(data_dir), session_id, resets_at, "strong", window)
                return {
                    "decision": "allow",
                    "reason": "Resuming the paused request; treat this as continuation, not a new task.",
                }
            return {"decision": "block", "reason": _choice_reason([])}

        # 4. First-time block when quota reaches strong threshold (<= 6%)
        strong_reasons = []
        for window, resets_at, reason in strong_windows:
            if _claim_marker(Path(data_dir), session_id, resets_at, "strong", window):
                _claim_pending_choice(Path(data_dir), session_id, resets_at, window)
                strong_reasons.append(reason)
        if strong_reasons:
            return {"decision": "block", "reason": _choice_reason(strong_reasons)}

        # 5. Soft warning above 6% and up to 15% (non-blocking)
        if primary:
            level = quota_warning(primary)
            resets_at = _number(primary.get("resets_at"))
            if level == "soft" and resets_at is not None and resets_at > time.time() and _claim_marker(
                Path(data_dir), session_id, resets_at, level, "five-hour"
            ):
                return {"decision": "allow", "reason": _soft_reason()}
        return ALLOW
    except Exception:
        return ALLOW


def handle_precompact(payload: dict, data_dir: Path) -> dict:
    """Return the V1 non-blocking warning for automatic compaction."""
    try:
        if not isinstance(payload, dict) or payload.get("trigger") != "auto":
            return ALLOW
        return {"decision": "allow", "reason": _strong_reason()}
    except Exception:
        return ALLOW


def handle_post_tool_use(payload: dict, data_dir: Path) -> dict:
    """Advise a handoff after a completed tool observes a strong quota window."""
    try:
        if not isinstance(payload, dict):
            return ALLOW
        if "agent_id" in payload:
            return ALLOW
        session_id = payload.get("session_id")
        turn_id = payload.get("turn_id")
        transcript_path = payload.get("transcript_path")
        if not isinstance(session_id, str) or not session_id:
            return ALLOW
        if not isinstance(turn_id, str) or not turn_id or not isinstance(transcript_path, str):
            return ALLOW
        primary = latest_primary_rate_limit(Path(transcript_path))
        secondary = latest_secondary_rate_limit(Path(transcript_path))

        active_resets = [
            r for r in (_number(s.get("resets_at")) if s else None for s in (primary, secondary))
            if r is not None and r > time.time()
        ]
        if any(_marker_exists(Path(data_dir), session_id, r, "user-continue") for r in active_resets):
            return ALLOW

        reasons = []
        for window, snapshot, level, reason in (
            ("five-hour", primary, quota_warning(primary) if primary else None,
             "Five-hour quota is nearly exhausted."),
            ("weekly", secondary,
             quota_warning(secondary, window_minutes=10080, soft_warning=False) if secondary else None,
             "Weekly quota is nearly exhausted."),
        ):
            if level != "strong":
                continue
            resets_at = _number(snapshot.get("resets_at"))
            if resets_at is None or resets_at <= time.time():
                continue
            if claim_strong_tool_stop(Path(data_dir), session_id, turn_id, resets_at, window):
                reasons.append(reason)
        if reasons:
            return {"decision": "allow", "reason": _tool_stop_reason(reasons), "tool_stop": True}
        return ALLOW
    except Exception:
        return ALLOW


def handle_pre_tool_use(payload: dict, data_dir: Path) -> dict:
    """Deny only an existing same-turn latch; never detect quota here."""
    try:
        if not isinstance(payload, dict) or "agent_id" in payload:
            return ALLOW
        session_id = payload.get("session_id")
        turn_id = payload.get("turn_id")
        if not isinstance(session_id, str) or not session_id:
            return ALLOW
        if not isinstance(turn_id, str) or not turn_id:
            return ALLOW
        latch_dir = _turn_latch_dir(Path(data_dir), session_id, turn_id)
        if any(marker.is_file() for marker in latch_dir.glob("*.marker")):
            return {
                "decision": "block",
                "reason": (
                    "This turn has already reached the quota guard. Stop expanding work, "
                    "summarize the current state, and ask the user to run $handoff-prepare "
                    "in a new turn before continuing."
                ),
            }
        return ALLOW
    except Exception:
        return ALLOW


def handle_event(payload: dict, data_dir: Path) -> dict:
    """Route a hook payload while retaining the direct V1 payload contract."""
    try:
        if not isinstance(payload, dict):
            return ALLOW
        event_name = payload.get("hook_event_name")
        if event_name == "PreCompact":
            return handle_precompact(payload, data_dir)
        if event_name == "PostToolUse":
            return handle_post_tool_use(payload, data_dir)
        if event_name == "PreToolUse":
            return handle_pre_tool_use(payload, data_dir)
        if event_name == "UserPromptSubmit":
            return handle_user_prompt(payload, data_dir)
        if event_name:
            return ALLOW
        if payload.get("trigger") == "auto":
            return handle_precompact(payload, data_dir)
        if "trigger" in payload:
            return ALLOW
        return handle_user_prompt(payload, data_dir)
    except Exception:
        return ALLOW


def _plugin_data_dir() -> Path:
    """Use Codex-provided plugin storage, with a stable local fallback."""
    configured = os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured)
    return Path.home() / ".codex" / "plugin-data" / "codex-handoff"


def format_hook_output(payload: dict, decision: dict) -> dict | None:
    """Translate internal decisions to the event's valid Codex JSON contract."""
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    event_name = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if event_name == "PostToolUse":
        return {
            "systemMessage": reason,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": reason,
            },
        }
    if event_name == "PreToolUse" and decision.get("decision") == "block":
        return {
            "systemMessage": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    if event_name in (None, "UserPromptSubmit") and decision.get("decision") == "block":
        return {"decision": "block", "reason": reason}
    return {"systemMessage": reason}


def main() -> None:
    """Read one hook payload from stdin and emit the Codex decision JSON."""
    try:
        # Codex sends JSON as UTF-8 bytes. Text-mode stdin can use a Windows
        # code page and silently corrupt non-ASCII user input.
        payload = json.load(sys.stdin.buffer)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        payload = {}
    output = format_hook_output(payload, handle_event(payload, _plugin_data_dir()))
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))


if __name__ == "__main__":
    main()
