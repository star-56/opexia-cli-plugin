# pxcore/calibration/ — ModelProfile load/save + the shipped pre-baked profiles.
#
# Two sources of a profile, both returning the same ModelProfile shape:
#   (A) pre-baked JSON shipped in profiles/ — fast, deterministic, for KNOWN models.
#   (B) derived on the customer's machine by battery.py against ANY model — the thing that
#       makes a brand-new / private / air-gapped model self-onboard without waiting on us.
#
# A model with NO profile from either source resolves to a conservative "unknown" profile
# whose fidelity scores are 0 — i.e. it images NOTHING until calibrated. Default-off, always.
from __future__ import annotations

import json
import os
from typing import Dict, Optional

from pxcore.types import Geometry, ModelProfile

_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "profiles")

# A model we have never seen images nothing. It is safe, not useless: run the battery (B) to
# earn imaging on. This is the correct direction to fail.
UNKNOWN_FLOOR = 0.90


def _geom(d: Dict) -> Geometry:
    return Geometry(
        page_w=int(d["page_w"]), page_h=int(d["page_h"]),
        cell_w=int(d["cell_w"]), cell_h=int(d["cell_h"]),
        resample_cap=int(d["resample_cap"]), pad=int(d.get("pad", 2)))


def _from_dict(d: Dict) -> ModelProfile:
    return ModelProfile(
        model_id=str(d["model_id"]),
        geometry=_geom(d["geometry"]),
        chars_per_vision_token=float(d["chars_per_vision_token"]),
        fidelity_scores={k: float(v) for k, v in d["fidelity_scores"].items()},
        fidelity_floor=float(d["fidelity_floor"]),
        calibrated_at=str(d.get("calibrated_at", "")),
        battery_version=int(d.get("battery_version", 1)),
        source=str(d.get("source", "prebaked")),          # type: ignore[arg-type]
    )


def to_dict(p: ModelProfile) -> Dict:
    g = p.geometry
    return {
        "model_id": p.model_id,
        "geometry": {"page_w": g.page_w, "page_h": g.page_h, "cell_w": g.cell_w,
                     "cell_h": g.cell_h, "resample_cap": g.resample_cap, "pad": g.pad},
        "chars_per_vision_token": p.chars_per_vision_token,
        "fidelity_scores": p.fidelity_scores,
        "fidelity_floor": p.fidelity_floor,
        "calibrated_at": p.calibrated_at,
        "battery_version": p.battery_version,
        "source": p.source,
    }


def unknown_profile(model_id: str) -> ModelProfile:
    """A never-seen model: images nothing (scores 0, floor high). Safe until calibrated."""
    return ModelProfile(
        model_id=model_id,
        geometry=Geometry(1568, 728, 8, 8, 1568, 2),
        # neutral density so the block reaches the FIDELITY gate and is refused there with the
        # honest "not proven safe" reason, rather than being quietly dropped as "unprofitable".
        chars_per_vision_token=3.1,
        fidelity_scores={"exact": 0.0, "gist": 0.0, "lookup": 0.0},
        fidelity_floor=UNKNOWN_FLOOR,
        source="prebaked",
    )


def _local_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".pxcore", "profiles")


def load_profile(model_id: str) -> ModelProfile:
    """Resolve order: locally-derived (B, freshest) → pre-baked (A) → unknown (image nothing).
    A locally-run battery result always wins over a shipped default for the same model."""
    safe = model_id.replace("/", "_").replace(":", "_")
    local = os.path.join(_local_dir(), f"{safe}.json")
    if os.path.exists(local):
        try:
            return _from_dict(json.loads(open(local, encoding="utf-8").read()))
        except (OSError, ValueError, KeyError):
            pass
    prebaked = os.path.join(_PROFILE_DIR, f"{safe}.json")
    if os.path.exists(prebaked):
        try:
            return _from_dict(json.loads(open(prebaked, encoding="utf-8").read()))
        except (OSError, ValueError, KeyError):
            pass
    return unknown_profile(model_id)


def save_local_profile(p: ModelProfile) -> str:
    """Persist a battery-derived profile (B) to the user's machine. Never leaves it."""
    d = _local_dir()
    os.makedirs(d, exist_ok=True)
    safe = p.model_id.replace("/", "_").replace(":", "_")
    path = os.path.join(d, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(p), f, indent=2)
    return path
