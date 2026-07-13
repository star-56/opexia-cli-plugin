# pxcore/integrations.py — last-mile glue: pxcore decisions -> provider message formats.
#
# The core's decide() returns KeepText | ImageWithFactsheet. Real code needs those as
# Anthropic / OpenAI message blocks. These helpers are that conversion, plus a whole-request
# compressor (Pattern A). This module lives in the CORE, so the proxy imports it — not the
# reverse — keeping the dependency direction right (proxy -> core).
#
# Every helper still obeys calibration: imaging happens only if the model's profile earned it.
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple

import pxcore
from pxcore.calibration import load_profile
from pxcore.types import BlockHint, ImageWithFactsheet, ModelProfile


# --- single-block helpers ---------------------------------------------------

def to_anthropic(text: str, profile: ModelProfile, *,
                 hint: Optional[BlockHint] = None) -> List[Dict[str, Any]]:
    """One block -> Anthropic content blocks. Image (+ factsheet text) if imaged, else text."""
    d = pxcore.decide(text, profile, hint=hint)
    if isinstance(d, ImageWithFactsheet):
        blocks: List[Dict[str, Any]] = [{
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.b64encode(d.png).decode("ascii")}}]
        if d.factsheet:
            blocks.append({"type": "text", "text": d.factsheet})
        return blocks
    return [{"type": "text", "text": text}]


def to_openai(text: str, profile: ModelProfile, *,
              hint: Optional[BlockHint] = None) -> List[Dict[str, Any]]:
    """One block -> OpenAI content parts (image as a data: URI, or text)."""
    d = pxcore.decide(text, profile, hint=hint)
    if isinstance(d, ImageWithFactsheet):
        uri = "data:image/png;base64," + base64.b64encode(d.png).decode("ascii")
        parts: List[Dict[str, Any]] = [{"type": "image_url", "image_url": {"url": uri}}]
        if d.factsheet:
            parts.append({"type": "text", "text": d.factsheet})
        return parts
    return [{"type": "text", "text": text}]


# --- whole-request compression (Pattern A / the proxy) ----------------------
#
# Walks an Anthropic /v1/messages body and images eligible reference bulk: the system prompt +
# tool docs, and historical tool_result / large text — never the final (active) turn. Splices
# images back cache-friendly (deterministic render -> byte-identical prefix -> cache still
# hits) and carries cache_control markers onto the spliced blocks. Never mutates the input.

def _image_block(png_b64: str, cache_control: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    b = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": png_b64}}
    if cache_control:
        b["cache_control"] = cache_control
    return b


def _text_block(text: str, cache_control: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    b = {"type": "text", "text": text}
    if cache_control:
        b["cache_control"] = cache_control
    return b


def _rewrite_text(text: str, profile: ModelProfile, *, hint: Optional[BlockHint],
                  cache_control: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    d = pxcore.decide(text, profile, hint=hint)
    if isinstance(d, ImageWithFactsheet):
        b64 = base64.b64encode(d.png).decode("ascii")
        blocks = [_image_block(b64, cache_control)]
        if d.factsheet:
            blocks.append(_text_block(d.factsheet))
        return blocks, d.saved_tokens
    return [_text_block(text, cache_control)], 0


def _rewrite_system(system: Any, profile: ModelProfile) -> Tuple[Any, int]:
    if isinstance(system, str):
        blocks, s = _rewrite_text(system, profile, hint=None, cache_control=None)
        return (blocks if s else system), s
    if isinstance(system, list):
        out, saved = [], 0
        for blk in system:
            if isinstance(blk, dict) and blk.get("type") == "text" and blk.get("text"):
                new, s = _rewrite_text(blk["text"], profile, hint=None,
                                       cache_control=blk.get("cache_control"))
                out.extend(new)
                saved += s
            else:
                out.append(blk)
        return out, saved
    return system, 0


def _rewrite_content_list(content: Any, profile: ModelProfile) -> Tuple[Any, int]:
    if isinstance(content, str):
        blocks, s = _rewrite_text(content, profile, hint=BlockHint(role="read_only"),
                                  cache_control=None)
        return (blocks if s else content), s
    if isinstance(content, list):
        out, saved = [], 0
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text" and blk.get("text"):
                new, s = _rewrite_text(blk["text"], profile, hint=BlockHint(role="read_only"),
                                       cache_control=blk.get("cache_control"))
                out.extend(new)
                saved += s
            elif isinstance(blk, dict) and blk.get("type") == "tool_result":
                rc, s = _rewrite_content_list(blk.get("content"), profile)
                nb = dict(blk)
                nb["content"] = rc
                out.append(nb)
                saved += s
            else:
                out.append(blk)
        return out, saved
    return content, 0


def compress_anthropic(body: Dict[str, Any], *, model: Optional[str] = None,
                       image_system: bool = True,
                       image_history: bool = True) -> Tuple[Dict[str, Any], int]:
    """Compress a full Anthropic /v1/messages body. Returns (new_body, tokens_saved).
    Pattern A as a pure library call — no proxy server, no network."""
    profile = load_profile(str(model or body.get("model", "")))
    new = dict(body)
    saved = 0

    if image_system and "system" in new:
        new["system"], s = _rewrite_system(new["system"], profile)
        saved += s

    messages = new.get("messages")
    if image_history and isinstance(messages, list) and messages:
        last = len(messages) - 1
        out_msgs = []
        for i, msg in enumerate(messages):
            if i == last or not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
                out_msgs.append(msg)
                continue
            nc, s = _rewrite_content_list(msg["content"], profile)
            nm = dict(msg)
            nm["content"] = nc
            out_msgs.append(nm)
            saved += s
        new["messages"] = out_msgs

    return new, saved
