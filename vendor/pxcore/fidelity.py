# pxcore/fidelity.py — the two-sided SAFETY gate.
#
# This is the module that makes "works on all vision models" mean "safely DECIDES per model"
# rather than "images on all models". It is default-OFF: a model x content-class is imaged
# only if calibration has PROVEN it safe. Everything else stays text — which, for content the
# model would confabulate, is the whole point.
from __future__ import annotations

from pxcore.types import BlockLabel, ModelProfile


def is_safe_to_image(label: BlockLabel, profile: ModelProfile) -> tuple:
    """(safe, reason). `reason` is always populated so a KeepText decision is never silent."""
    # 1. Exact content must be reproducible byte-for-byte. Vision confabulates. Never image.
    if label.fidelity_class == "exact":
        return False, "exact-fidelity content stays text (vision confabulates verbatim strings)"

    # 2. Edit targets: a single wrong glyph becomes a wrong edit, with no error raised.
    if label.role == "edit_target":
        return False, "edit-target content stays text (a misread glyph becomes a wrong edit)"

    # 3. Reference content: image only if THIS model clears the fidelity floor for reference.
    score = profile.fidelity("reference")
    if score < profile.fidelity_floor:
        return (False,
                f"model '{profile.model_id}' reference fidelity {score:.2f} is below its "
                f"floor {profile.fidelity_floor:.2f} - not proven safe, staying text")

    return True, f"reference fidelity {score:.2f} >= floor {profile.fidelity_floor:.2f}"
