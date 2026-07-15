# pxcore/gate.py — the profitability decision (is imaging a token WIN?).
#
# Separate from the safety decision (fidelity.py) on purpose: a block can be perfectly safe
# to image and still not worth imaging (small, or content whose text is already cheaper per
# token than the image would be). This module only answers "does it save tokens?", never
# "is it safe?".
from __future__ import annotations

from pxcore.types import BlockLabel, ModelProfile

# Below this the fixed image cost is not worth it — a 40-char command result imaged costs
# more than it saves. Tunable, but a floor must exist or we image trivia and lose money.
DEFAULT_SIZE_FLOOR_CHARS = 1500


def is_profitable(label: BlockLabel, profile: ModelProfile, text_len: int,
                  *, size_floor_chars: int = DEFAULT_SIZE_FLOOR_CHARS) -> bool:
    """Is imaging this block a token win? DENSITY-AGNOSTIC — prose and dense content are judged
    on the SAME economics decide()'s final net-loss guard uses: imaged chars/token vs this
    block's own text chars/token.

    This used to hard-reject any non-'dense' block ('sparse prose never wins'). That was true
    only against a pessimistic chars/2.5 image estimate the renderer no longer uses, and it
    silently left real prose savings on the table: a page images at ~750/(cell_w*cell_h) chars
    per vision token (measured ~11.5 at 8x8 on gpt-4o) while prose text is only ~3.9 chars/
    token — so imaging prose is a ~3x WIN whenever the model's geometry supports it. The old
    rule also compared against the profile's PROVISIONAL chars_per_vision_token (a placeholder,
    e.g. 3.1) while the net-loss guard used the geometry (w*h)/750 — two different cost bases
    for the same image. This aligns the gate to the geometry basis so the early gate (here) and
    the final guard (decide() §3) agree."""
    if text_len < size_floor_chars:
        return False
    # Image cost basis IDENTICAL to decide()'s §3 net-loss guard: a full page costs (w*h)/750
    # tokens (Anthropic's billed formula) and holds cols*rows glyphs, so imaged text packs
    # ~750/(cell_w*cell_h) chars per vision token. Blank pixels cost the same as inked ones, so
    # this density is independent of prose-vs-dense — narrower prose just renders taller for the
    # same char count.
    g = profile.geometry
    image_chars_per_token = 750.0 / max(1.0, float(g.cell_w * g.cell_h))
    # This block's OWN text density, content-aware: est_text_tokens already separates prose
    # (~3.9 c/t) from code/json/logs (~1-2 c/t), so this is never optimistic on prose.
    text_chars_per_token = text_len / max(1, label.est_text_tokens)
    # Image only when it genuinely packs more chars per token than the text does. §3 re-checks
    # this against the ACTUAL rendered dimensions and is the authoritative net-loss backstop, so
    # a marginal pass here can never image at a net loss — only waste a render.
    return image_chars_per_token > text_chars_per_token
