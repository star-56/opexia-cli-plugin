# pxcore/fidelity.py — the two-sided SAFETY gate.
#
# This is the module that makes "works on all vision models" mean "safely DECIDES per model"
# rather than "images on all models". It is default-OFF: a model x content-class is imaged
# only if calibration has PROVEN it safe. Everything else stays text — which, for content the
# model would confabulate, is the whole point.
from __future__ import annotations

from pxcore.types import BlockLabel, ModelProfile


def is_safe_to_image(label: BlockLabel, profile: ModelProfile) -> tuple:
    """(safe, reason). `reason` is always populated so a KeepText decision is never silent.

    The safety bar is per CONTENT CLASS, because a model's imaged-reading fidelity is not one
    number: it reads gist content reliably and lookup content unreliably. So a gist block is
    gated by the model's measured GIST fidelity, a lookup block by its (much harder) LOOKUP
    fidelity. This is what lets a gist-strong model image the content it's good at while its
    weak lookups still correctly stay text."""
    # 1. Exact content must be reproducible byte-for-byte. Vision confabulates. Never image.
    if label.fidelity_class == "exact":
        return False, "exact-fidelity content stays text (vision confabulates verbatim strings)"

    # 2. Edit targets: a single wrong glyph becomes a wrong edit, with no error raised.
    if label.role == "edit_target":
        return False, "edit-target content stays text (a misread glyph becomes a wrong edit)"

    # 3. gist / lookup: gate against the model's fidelity for THIS class.
    cls = label.fidelity_class          # "gist" or "lookup"
    score = profile.fidelity(cls)
    if score < profile.fidelity_floor:
        return (False,
                f"model '{profile.model_id}' {cls} fidelity {score:.2f} is below its floor "
                f"{profile.fidelity_floor:.2f} - not proven safe, staying text")
    return True, f"{cls} fidelity {score:.2f} >= floor {profile.fidelity_floor:.2f}"
