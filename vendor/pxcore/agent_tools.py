# pxcore/agent_tools.py — Pattern B for Python: ready-to-register agent tools.
#
# Register these as tools in any Python agent framework (LangGraph, CrewAI, OpenAI Agents,
# raw Anthropic tool-use). The agent calls them; each does the operation and returns the
# result token-efficiently as Anthropic content blocks (image + factsheet, or text). Because
# they return content BLOCKS, the calling model must be one whose tool results accept image
# blocks (Anthropic does); on a provider whose tool results are text-only, pass
# `as_text=True` to get plain text (still safe, just uncompressed).
from __future__ import annotations

import os
from typing import Any, Dict, List, Union

from pxcore import integrations, ops
from pxcore.calibration import load_profile
from pxcore.types import BlockHint

_MODEL = os.environ.get("PXCORE_MODEL", "claude-fable-5")


def _emit(text: str, header: str, *, hint=None, as_text: bool = False
          ) -> Union[str, List[Dict[str, Any]]]:
    profile = load_profile(_MODEL)
    if as_text:
        return header + text
    blocks = integrations.to_anthropic(header + text if not header else text, profile, hint=hint)
    # keep the header as a leading text note when we imaged (so the block is identifiable)
    if header and blocks and blocks[0].get("type") == "image":
        return [{"type": "text", "text": header.strip()}, *blocks]
    return blocks


def read(path: str, *, as_text: bool = False):
    text, header = ops.read_file(path)
    return _emit(text, header, as_text=as_text)


def run(command: str, *, timeout: float = 120.0, as_text: bool = False):
    text, header = ops.run_command(command, timeout)
    return _emit(text, header, as_text=as_text)


def grep(pattern: str, path: str = ".", *, as_text: bool = False):
    text, header = ops.grep_files(pattern, path)
    return _emit(text, header, as_text=as_text)


def view(text: str, *, exact: bool = False, as_text: bool = False):
    hint = BlockHint(fidelity_class="exact") if exact else None
    return _emit(text, "", hint=hint, as_text=as_text)
