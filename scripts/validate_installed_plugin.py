#!/usr/bin/env python3
"""Run the plugin tests from a repository-free, space-containing install path."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = REPOSITORY_ROOT / "plugins" / "codex-handoff"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex handoff install ") as directory:
        plugin_root = Path(directory) / "marketplace cache" / "codex-handoff"
        shutil.copytree(PLUGIN_SOURCE, plugin_root)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=plugin_root,
            check=False,
        )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
