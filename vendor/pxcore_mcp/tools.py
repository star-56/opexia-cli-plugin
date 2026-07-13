# pxcore_mcp/tools.py — the imaged-result tools, backed by the shared core.
#
# Each tool does the real operation (read a file, run a command, grep), then hands the result
# to pxcore.decide(). If the core says image, the tool returns an MCP image content block plus
# a text factsheet of the exact spans; otherwise it returns the result as text. The model
# reads the image with its native vision — the token saving is on the tool RESULT, which is
# all an MCP tool can touch (the system prompt / history are already sent; see the design).
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import pxcore
from pxcore import ops
from pxcore.calibration import load_profile
from pxcore.meter import Meter
from pxcore.types import BlockHint, ImageWithFactsheet

_MODEL = os.environ.get("PXCORE_MODEL", "claude-fable-5")
_PROFILE = load_profile(_MODEL)
_METER = Meter()


def _content_for(text: str, *, hint: Optional[BlockHint] = None,
                 header: str = "") -> List[Dict[str, Any]]:
    """Run the core decision and shape MCP content blocks. Always includes a small text note
    so the model knows what it is looking at and that exact ids are in the factsheet."""
    decision = pxcore.decide(text, _PROFILE, hint=hint, meter=_METER)
    if isinstance(decision, ImageWithFactsheet):
        note = (f"{header}[pxcore: imaged to save ~{decision.saved_tokens} tokens; "
                f"exact identifiers are listed as text below]").strip()
        blocks: List[Dict[str, Any]] = [
            {"type": "text", "text": note},
            {"type": "image", "data": base64.b64encode(decision.png).decode("ascii"),
             "mimeType": "image/png"},
        ]
        if decision.factsheet:
            blocks.append({"type": "text", "text": decision.factsheet})
        return blocks
    # KeepText — return the content verbatim as text.
    body = (header + text) if header else text
    return [{"type": "text", "text": body}]


# --- tool implementations ---------------------------------------------------

def tool_read(arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    # a file the agent asked to READ is reference by default; if it will edit it, it should
    # use its native editor, not this tool.
    text, header = ops.read_file(str(arguments.get("path", "")))
    return _content_for(text, header=header)


def tool_run(arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    text, header = ops.run_command(str(arguments.get("command", "")),
                                   float(arguments.get("timeout", 120)))
    return _content_for(text, header=header)


def tool_grep(arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    text, header = ops.grep_files(str(arguments.get("pattern", "")),
                                  str(arguments.get("path", ".")))
    return _content_for(text, header=header)


def tool_view(arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Image an arbitrary block the agent already has in hand (e.g. a large payload it built),
    to keep it cheap in context. Honors an explicit fidelity hint from the caller."""
    text = str(arguments.get("text", ""))
    hint = None
    if arguments.get("exact"):
        hint = BlockHint(fidelity_class="exact")
    return _content_for(text, hint=hint)


TOOLS = [
    {
        "name": "pxcore_read",
        "description": ("Read a file and return it token-efficiently. Large dense files come "
                        "back as an image (read via your native vision) with exact identifiers "
                        "listed as text; small or exact-heavy files come back as plain text. "
                        "Use for reference reads you will NOT edit verbatim."),
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "file path to read"}},
            "required": ["path"]},
        "_handler": tool_read,
    },
    {
        "name": "pxcore_run",
        "description": ("Run a shell command and return its output token-efficiently (large "
                        "dense output as an image, exact ids as text)."),
        "inputSchema": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "number", "description": "seconds (default 120)"}},
            "required": ["command"]},
        "_handler": tool_run,
    },
    {
        "name": "pxcore_grep",
        "description": "Search files under a path and return matches token-efficiently.",
        "inputSchema": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"]},
        "_handler": tool_grep,
    },
    {
        "name": "pxcore_view",
        "description": ("Render a large block you already have into a token-efficient image. "
                        "Set exact=true to force it to stay text (for content that must be "
                        "reproduced verbatim)."),
        "inputSchema": {"type": "object", "properties": {
            "text": {"type": "string"}, "exact": {"type": "boolean"}},
            "required": ["text"]},
        "_handler": tool_view,
    },
]

HANDLERS = {t["name"]: t["_handler"] for t in TOOLS}
TOOL_SPECS = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]
