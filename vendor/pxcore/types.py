# pxcore/types.py — the plain dataclasses every module speaks.
#
# Kept dependency-free and dumb on purpose: modules communicate ONLY through these, so a
# change inside one module cannot reach into another except through a typed value. That is
# what lets each layer be reasoned about and swapped alone.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple, Union

# --- classification axes ----------------------------------------------------

Density = Literal["dense", "sparse"]
FidelityClass = Literal["exact", "reference"]
Role = Literal["edit_target", "read_only"]


@dataclass(frozen=True)
class BlockHint:
    """An adapter override for the classifier — it often knows more than a heuristic can
    (e.g. 'this is the file the user is actively editing' → force exact/edit_target)."""
    fidelity_class: Optional[FidelityClass] = None
    role: Optional[Role] = None
    is_code: Optional[bool] = None


@dataclass(frozen=True)
class BlockLabel:
    density: Density
    fidelity_class: FidelityClass
    role: Role
    est_text_tokens: int
    exact_spans: Tuple[str, ...] = ()      # ids/paths/hashes found inside — for the factsheet


# --- geometry + profile -----------------------------------------------------

@dataclass(frozen=True)
class Geometry:
    page_w: int                 # px
    page_h: int                 # px
    cell_w: int                 # px per glyph cell (monospace)
    cell_h: int
    resample_cap: int           # max px on the long edge the API actually ingests
    pad: int = 2                # px margin

    @property
    def cols(self) -> int:
        return max(1, (self.page_w - 2 * self.pad) // self.cell_w)

    @property
    def rows(self) -> int:
        return max(1, (self.page_h - 2 * self.pad) // self.cell_h)


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    geometry: Geometry
    chars_per_vision_token: float           # measured density of imaged dense text
    fidelity_scores: Dict[str, float]       # {"exact": 0..1, "reference": 0..1} pass-rates
    fidelity_floor: float                   # the enable threshold
    calibrated_at: str = ""                 # ISO date; "" = never run a real battery
    battery_version: int = 1
    # "provisional" = shipped defaults with scores that DO NOT enable imaging until a real
    # battery run has been done. It is honest by construction: no measurement, no imaging.
    source: Literal["prebaked", "local", "provisional"] = "prebaked"

    def fidelity(self, cls: FidelityClass) -> float:
        return float(self.fidelity_scores.get(cls, 0.0))


# --- render + decision ------------------------------------------------------

@dataclass(frozen=True)
class Rendered:
    png: bytes
    factsheet: str
    width: int
    height: int
    est_image_tokens: int


@dataclass(frozen=True)
class KeepText:
    reason: str                 # why we did NOT image — always stated, never silent
    label: Optional[BlockLabel] = None


@dataclass(frozen=True)
class ImageWithFactsheet:
    png: bytes
    factsheet: str              # verbatim exact spans, as text, beside the image
    saved_tokens: int
    width: int
    height: int
    label: Optional[BlockLabel] = None


Decision = Union[KeepText, ImageWithFactsheet]


# --- calibration ------------------------------------------------------------

@dataclass(frozen=True)
class Probe:
    """One calibration item. The core defines the image + the exact expected answer + the
    scorer; the ADAPTER supplies the model call (only it holds the connection)."""
    probe_id: str
    fidelity_class: FidelityClass
    png: bytes
    prompt: str                 # what to ask the model about the image
    expected: str               # ground truth
    scorer: Literal["exact", "numeric", "keyword_overlap"] = "exact"


@dataclass
class ProbeResult:
    probe_id: str
    fidelity_class: FidelityClass
    passed: bool
