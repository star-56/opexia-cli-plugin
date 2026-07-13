# pxcore/classifier.py — label a content block on three axes, deterministically.
#
# No model, no network. Heuristics + regex only. The three axes are what the downstream
# safety decision turns on: density (is imaging even a token win?), fidelity_class (must the
# model reproduce this byte-for-byte?), and role (will it EDIT this?).
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from pxcore.renderer import extract_exact_spans
from pxcore.types import BlockHint, BlockLabel


def _line_shape(line: str) -> str:
    """Normalize a line to its structural shape: digits -> #, quoted strings -> "", collapsed
    whitespace. Two rows of a uniform table map to the same shape."""
    s = re.sub(r"\d+", "#", line)
    s = re.sub(r'"[^"]*"', '""', s)
    s = re.sub(r"\s+", " ", s.strip())
    return s[:48]


_KEY_FIELD = re.compile(r'"(?:\w*_?id|key|uuid|name|code)"\s*:', re.I)


def _is_lookup(text: str) -> bool:
    """Is this a keyed record-set someone would query by key (the lookup-risk structure)?
    Requires BOTH: (a) uniform rows (one dominant line-shape), AND (b) most rows carry an
    explicit id/key field. Free-form logs are uniform but NOT keyed, so they default to gist
    (which is correct — logs are read for comprehension, and imaging them is a real, safe
    saving that pxpipe exploits). Default gist, escalate to lookup only on a clear signal."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 20:
        return False
    shapes = Counter(_line_shape(ln) for ln in lines)
    uniform = shapes.most_common(1)[0][1] / len(lines) > 0.5
    if not uniform:
        return False
    keyed = sum(1 for ln in lines if _KEY_FIELD.search(ln))
    return keyed / len(lines) > 0.5

# Token estimate without a tokenizer dep. CONTENT-AWARE chars/token, derived from the
# non-alphabetic character ratio: prose is mostly long alpha words (~3.8-4 chars/token),
# while code/JSON/logs are symbol/digit/quote heavy and tokenize denser (~2.6 chars/token).
# This is what the FINAL net-loss guard in decide() trusts, so it must NOT be optimistic on
# prose — over-imaging prose is a real token INCREASE, not a saving (measured: a markdown
# chunk imaged at chars/2.5 came out +12.6% tokens). A flat divisor could not tell prose from
# JSON; this ratio can.
def _est_tokens(text: str) -> int:
    non_space = sum(1 for c in text if not c.isspace())
    if non_space == 0:
        return 1
    alpha = sum(1 for c in text if c.isalpha())
    non_alpha_ratio = (non_space - alpha) / non_space
    cpt = 4.0 - 1.4 * min(1.0, non_alpha_ratio / 0.45)
    return max(1, int(len(text) / cpt))


_CODE_MARKERS = re.compile(
    r"[{}();]|=>|::|def |class |function |import |const |return |</?\w+>|^\s*[#/*]",
    re.M)
_JSON_MARKERS = re.compile(r'^\s*[\[{].*[\]}]\s*$', re.S)
_LOG_MARKERS = re.compile(
    r"\b(INFO|DEBUG|WARN|WARNING|ERROR|TRACE|FATAL)\b|\d{4}-\d\d-\d\d[ T]\d\d:\d\d")


def _density(text: str) -> str:
    """dense = low chars/token (code, json, logs, dense output). We approximate token density
    by symbol ratio: dense content is punctuation/identifier heavy, prose is word/space heavy."""
    if not text:
        return "sparse"
    non_space = sum(1 for c in text if not c.isspace())
    symbols = sum(1 for c in text if not c.isalnum() and not c.isspace())
    words = len(re.findall(r"[A-Za-z]{3,}", text))
    avg_word_gap = non_space / max(1, words)
    symbol_ratio = symbols / max(1, non_space)
    looks_code = bool(_CODE_MARKERS.search(text)) or bool(_JSON_MARKERS.match(text.strip()))
    looks_log = bool(_LOG_MARKERS.search(text))
    if looks_code or looks_log or symbol_ratio > 0.18 or avg_word_gap < 3.2:
        return "dense"
    return "sparse"


def classify(text: str, hint: Optional[BlockHint] = None) -> BlockLabel:
    hint = hint or BlockHint()
    density = _density(text)

    exact_spans = tuple(extract_exact_spans(text))

    # fidelity_class — the three-way split. The adapter's hint wins (it knows the task); else:
    #   EXACT   if dominated by verbatim tokens (ids/hashes/paths);
    #   LOOKUP  if it is a large UNIFORM table/record list (find-value-by-key is the risk);
    #   GIST    otherwise (code/logs/varied output the model reads to reason over).
    if hint.fidelity_class is not None:
        fidelity_class = hint.fidelity_class
    else:
        exact_chars = sum(len(s) for s in exact_spans)
        density_of_exact = exact_chars / max(1, len(text))
        if density_of_exact > 0.25:
            fidelity_class = "exact"
        elif _is_lookup(text):
            # a uniform KEYED record-set — the model can't reliably locate one row by key in a
            # dense image, so this needs the (high) lookup fidelity bar.
            fidelity_class = "lookup"
        else:
            fidelity_class = "gist"

    # role: edit_target if the adapter says so, or it looks like a source file body.
    if hint.role is not None:
        role = hint.role
    else:
        role = "read_only"        # default; adapters mark edit targets explicitly

    return BlockLabel(
        density=density,
        fidelity_class=fidelity_class,
        role=role,
        est_text_tokens=_est_tokens(text),
        exact_spans=exact_spans,
    )
