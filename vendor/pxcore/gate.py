# pxcore/gate.py — the profitability decision (is imaging a token WIN?).
#
# Separate from the safety decision (fidelity.py) on purpose: a block can be perfectly safe
# to image and still not worth imaging (small, or sparse prose that is already cheap as
# text). This module only answers "does it save tokens?", never "is it safe?".
from __future__ import annotations

from pxcore.types import BlockLabel, ModelProfile

# Below this the fixed image cost is not worth it — a 40-char command result imaged costs
# more than it saves. Tunable, but a floor must exist or we image trivia and lose money.
DEFAULT_SIZE_FLOOR_CHARS = 1500


def is_profitable(label: BlockLabel, profile: ModelProfile, text_len: int,
                  *, size_floor_chars: int = DEFAULT_SIZE_FLOOR_CHARS) -> bool:
    # sparse prose is ~3.5 chars/token already — imaging it never wins.
    if label.density != "dense":
        return False
    if text_len < size_floor_chars:
        return False
    # dense text at ~1 char/token vs the model's measured imaged density. Only a win if the
    # image packs more chars per token than text does.
    text_chars_per_token = 1.0        # dense text, conservative
    if profile.chars_per_vision_token <= text_chars_per_token:
        return False
    return True
