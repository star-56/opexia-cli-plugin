# pxcore — deterministic image-as-context token compression (shared core).
#
# One public question, answered per content block:  IMAGE this, or KEEP it as text?
#
#   decide(block, profile) -> KeepText(reason)  |  ImageWithFactsheet(png, factsheet, saved)
#
# Pipeline:  classify -> profitable? -> safe? -> render(+factsheet) -> meter
# No LLM anywhere in this path. No third-party import in the core. Every KeepText states a
# reason; imaging is default-off and earned by calibration.
from __future__ import annotations

from typing import List, Optional

from pxcore import gate as _gate
from pxcore.classifier import classify
from pxcore.drift import DriftMonitor
from pxcore.fidelity import is_safe_to_image
from pxcore.meter import Meter
from pxcore.renderer import render
from pxcore.renderer import fits_one_page as _fits_one_page
from pxcore.renderer import paginate as _paginate
from pxcore.types import (
    BlockHint, BlockLabel, Decision, Geometry, ImageWithFactsheet, KeepText,
    ModelProfile, Rendered,
)

__all__ = [
    "decide", "decide_paged", "classify", "render", "Meter", "DriftMonitor",
    "BlockHint", "BlockLabel", "Decision", "Geometry", "ImageWithFactsheet",
    "KeepText", "ModelProfile", "Rendered",
    # in-code integration (Pattern A) — imported lazily below to avoid an import cycle
    "to_anthropic", "to_openai", "compress_anthropic",
]

__version__ = "0.1.0"

# A single oversized block paginates into at most this many page-images before we give up and
# keep the whole thing as text. A ceiling exists so a pathological megablock cannot explode
# into hundreds of images; each page below the cap still images only if IT alone wins, so this
# is a blast-radius guard, not an economic one.
DEFAULT_MAX_PAGES = 16


def __getattr__(name: str):
    # lazy re-export: integrations imports pxcore, so bind these on first access, not at
    # module load, to avoid a circular import.
    if name in ("to_anthropic", "to_openai", "compress_anthropic"):
        from pxcore import integrations
        return getattr(integrations, name)
    raise AttributeError(f"module 'pxcore' has no attribute {name!r}")


def decide(block: str, profile: ModelProfile, *,
           hint: Optional[BlockHint] = None,
           meter: Optional[Meter] = None,
           drift: Optional[DriftMonitor] = None) -> Decision:
    """Decide image-vs-text for one block. Deterministic given (block, profile)."""
    label = classify(block, hint)

    # 1. profitability — is imaging even a token win?
    if not _gate.is_profitable(label, profile, len(block)):
        return _keep(meter, profile, label,
                     "not a token win (sparse or below size floor)")

    # 2. safety — is imaging PROVEN safe for this model x class?
    safe, reason = is_safe_to_image(label, profile)
    if not safe:
        return _keep(meter, profile, label, reason)

    # 2b. live drift override — a model that is failing probes NOW is demoted regardless of
    # what its stored profile claims. Checked against THIS block's content class.
    if drift is not None and drift.is_demoted(profile.model_id, label.fidelity_class,
                                              profile.fidelity_floor):
        return _keep(meter, profile, label,
                     f"{label.fidelity_class} fidelity has drifted below floor - demoted to text")

    # 2c. one-page fit — never silently truncate imaged content. A block too big for a capped
    # page stays text; dropping imaged rows with no error is the exact failure we forbid.
    if not _fits_one_page(block, profile.geometry):
        return _keep(meter, profile, label,
                     "too large for one page at the resample cap - staying text (no silent "
                     "truncation)")

    # 3. render, then the FINAL profitability check against real dimensions. The gate in §1
    # used a density heuristic; only now do we know the actual image-token cost. Narrow/short
    # or not-dense-enough content can render to a page whose pixel cost >= the text it
    # replaces — imaging that would INCREASE tokens. Never image at a net loss.
    r: Rendered = render(block, profile.geometry, with_factsheet=True)
    saved = label.est_text_tokens - r.est_image_tokens
    if saved <= 0:
        return _keep(meter, profile, label,
                     "imaging would not reduce tokens for this content "
                     "(image cost >= text cost)")
    if meter is not None:
        meter.record(model_id=profile.model_id, decision="image",
                     text_tokens=label.est_text_tokens, image_tokens=r.est_image_tokens,
                     saved=saved, reason=reason)
    return ImageWithFactsheet(png=r.png, factsheet=r.factsheet, saved_tokens=saved,
                              width=r.width, height=r.height, label=label)


def decide_paged(block: str, profile: ModelProfile, *,
                 hint: Optional[BlockHint] = None,
                 meter: Optional[Meter] = None,
                 drift: Optional[DriftMonitor] = None,
                 max_pages: int = DEFAULT_MAX_PAGES) -> List[Decision]:
    """Multi-page decide: paginate an oversized block into page-sized chunks and run the FULL
    decide() pipeline on each. Returns one Decision per page (a list of length 1 for a block
    that already fits one page — so callers can treat single- and multi-page uniformly).

    This is how content bigger than one page gets imaged instead of falling to keep-text: each
    page is classified, safety-gated, one-page-fit-checked and net-loss-guarded on its OWN, so
    a page images only if it alone is safe and a token win. No silent truncation — paginate()
    places every row on exactly one page. Above max_pages the whole block stays text with a
    stated reason (a blast-radius ceiling, never a silent drop)."""
    pages = _paginate(block, profile.geometry)
    if len(pages) <= 1:
        return [decide(block, profile, hint=hint, meter=meter, drift=drift)]
    if max_pages and len(pages) > max_pages:
        return [_keep(meter, profile, classify(block, hint),
                      f"block needs {len(pages)} pages (> cap {max_pages}) - staying text "
                      "(no silent truncation)")]
    return [decide(pg, profile, hint=hint, meter=meter, drift=drift) for pg in pages]


def _keep(meter: Optional[Meter], profile: ModelProfile, label: BlockLabel,
          reason: str) -> KeepText:
    if meter is not None:
        meter.record(model_id=profile.model_id, decision="text",
                     text_tokens=label.est_text_tokens, image_tokens=0, saved=0,
                     reason=reason)
    return KeepText(reason=reason, label=label)
