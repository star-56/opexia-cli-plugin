# pxcore/ops.py — the raw operations (read/run/grep), one source of truth.
#
# These do the actual work and return plain text + a header. The library tools, the MCP
# tools, and (indirectly) anything else all funnel through here, so behaviour cannot drift
# between the delivery surfaces. No pxcore-decision logic lives here — this is just "get the
# text"; the imaging decision is layered on top by integrations/agent_tools/mcp.
from __future__ import annotations

import os
import re
import subprocess
from typing import Tuple

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


def read_file(path: str) -> Tuple[str, str]:
    """(text, header). Header names the source so an imaged block is still identifiable."""
    if not path or not os.path.isfile(path):
        return f"pxcore: no such file: {path}", ""
    try:
        return open(path, "r", encoding="utf-8", errors="replace").read(), f"# {path}\n"
    except OSError as e:
        return f"pxcore: {e}", ""


def run_command(command: str, timeout: float = 120.0) -> Tuple[str, str]:
    if not command:
        return "pxcore: no command", ""
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"pxcore: timed out: {command}", ""
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    return out, f"$ {command}  (exit {p.returncode})\n"


def grep_files(pattern: str, path: str = ".", limit: int = 5000) -> Tuple[str, str]:
    if not pattern:
        return "pxcore: no pattern", ""
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"pxcore: bad pattern: {e}", ""
    hits = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                for i, line in enumerate(open(fp, "r", encoding="utf-8", errors="replace"), 1):
                    if rx.search(line):
                        hits.append(f"{fp}:{i}: {line.rstrip()}")
                        if len(hits) >= limit:
                            break
            except OSError:
                continue
    body = "\n".join(hits) if hits else "(no matches)"
    return body, f"grep {pattern!r} in {path}\n"
