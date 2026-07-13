# pxcore/calibration/battery.py — the portable, self-scoring calibration battery (B).
#
# The core DEFINES the probes (image + ground truth + scorer) and DERIVES a profile from the
# results; the ADAPTER supplies the model call, because only it holds the connection. This
# split is what lets the exact-same battery calibrate a hosted Claude, a private fine-tune,
# or an air-gapped model — the core never needs to talk to any model itself.
#
# Scoring is exact-match / numeric / keyword-overlap — NO LLM judge. A fidelity gate that is
# itself judged by an LLM would be neither deterministic nor zero-egress.
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from pxcore.renderer import render
from pxcore.types import Geometry, ModelProfile, Probe, ProbeResult

BATTERY_VERSION = 1

# Candidate geometries the sweep tries. Long edge stays within a conservative resample cap.
_GEOMETRIES = [
    Geometry(1568, 728, 7, 7, 1568, 2),
    Geometry(1568, 728, 8, 8, 1568, 2),
    Geometry(1568, 728, 10, 10, 1568, 2),
    Geometry(768, 1024, 8, 8, 1024, 2),
]


# --- probe content (deterministic; no randomness so a run is reproducible) --

def _arith_items() -> List[Tuple[str, str]]:
    # novel arithmetic — dense-numeric reading. Deterministic operands.
    out = []
    for i in range(1, 21):
        a, b = 1000 + i * 37, 700 + i * 53
        out.append((f"{a} + {b} = ?", str(a + b)))
    return out


def _hex_items() -> List[Tuple[str, str]]:
    # verbatim 12-char hex — THE exact-string gate. If a model fails this, exact content
    # must never be imaged for it (it already never is, but this measures the risk).
    out = []
    base = "0123456789abcdef"
    for i in range(15):
        s = "".join(base[(i * 7 + j * 3) % 16] for j in range(12))
        out.append((f"Repeat the hex string exactly: {s}", s))
    return out


def _state_items() -> List[Tuple[str, str]]:
    # state tracking — a small table of key=value the model reads back after mutations.
    out = []
    for i in range(10):
        k = f"k{i}"
        v = str(100 + i * 11)
        table = "\n".join(f"{k2}={100 + j * 11}" for j, k2 in enumerate(f"k{n}" for n in range(10)))
        out.append((f"{table}\n\nWhat is the value of {k}?", v))
    return out


def build_probes(geometry: Geometry) -> List[Probe]:
    probes: List[Probe] = []
    for i, (q, a) in enumerate(_arith_items()):
        r = render(q, geometry, with_factsheet=False)
        probes.append(Probe(f"arith_{i}", "reference", r.png,
                            "Read the arithmetic in the image and give only the number.",
                            a, "numeric"))
    for i, (q, a) in enumerate(_hex_items()):
        r = render(q, geometry, with_factsheet=False)
        probes.append(Probe(f"hex_{i}", "exact", r.png,
                            "Read the hex string in the image and repeat it exactly.",
                            a, "exact"))
    for i, (q, a) in enumerate(_state_items()):
        r = render(q, geometry, with_factsheet=False)
        probes.append(Probe(f"state_{i}", "reference", r.png,
                            "Read the table in the image and answer.", a, "exact"))
    return probes


# --- scoring ----------------------------------------------------------------

def _num(s: str) -> Optional[int]:
    m = re.search(r"-?\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None


def score(probe: Probe, model_answer: str) -> bool:
    ans = (model_answer or "").strip()
    if probe.scorer == "numeric":
        a, e = _num(ans), _num(probe.expected)
        return a is not None and a == e
    if probe.scorer == "keyword_overlap":
        want = set(re.findall(r"\w+", probe.expected.lower()))
        got = set(re.findall(r"\w+", ans.lower()))
        return bool(want) and len(want & got) / len(want) >= 0.7
    # exact: the answer must contain the expected string verbatim (models add prose).
    return probe.expected in ans


# --- profile derivation -----------------------------------------------------

def aggregate(results: List[ProbeResult]) -> Dict[str, float]:
    """pass-rate per fidelity_class."""
    by: Dict[str, List[bool]] = {}
    for r in results:
        by.setdefault(r.fidelity_class, []).append(r.passed)
    return {k: (sum(v) / len(v) if v else 0.0) for k, v in by.items()}


def derive_profile(model_id: str, geometry: Geometry, results: List[ProbeResult], *,
                   chars_per_vision_token: float, fidelity_floor: float = 0.9,
                   calibrated_at: str = "") -> ModelProfile:
    scores = aggregate(results)
    scores.setdefault("exact", 0.0)
    scores.setdefault("reference", 0.0)
    return ModelProfile(
        model_id=model_id,
        geometry=geometry,
        chars_per_vision_token=chars_per_vision_token,
        fidelity_scores=scores,
        fidelity_floor=fidelity_floor,
        calibrated_at=calibrated_at,
        battery_version=BATTERY_VERSION,
        source="local",
    )


# --- the adapter-facing runner ----------------------------------------------

# The adapter passes a callable that takes (prompt, png_bytes) and returns the model's text
# answer. The core never calls a model itself; it only defines probes and scores answers.
AskModel = Callable[[str, bytes], str]


def run_battery(model_id: str, ask: AskModel, *,
                geometries: Optional[List[Geometry]] = None,
                chars_per_vision_token: float = 3.1,
                fidelity_floor: float = 0.9,
                calibrated_at: str = "") -> ModelProfile:
    """GEOMETRY SWEEP + scoring. Runs the battery at each candidate geometry, keeps the one
    whose reference pass-rate clears the floor with the most chars/token (densest safe page).
    Falls back to the highest-fidelity geometry if none clears the floor (it will simply
    image nothing — safe)."""
    geometries = geometries or _GEOMETRIES
    best: Optional[Tuple[ModelProfile, float]] = None

    for g in geometries:
        probes = build_probes(g)
        results = [ProbeResult(p.probe_id, p.fidelity_class, score(p, ask(p.prompt, p.png)))
                   for p in probes]
        prof = derive_profile(model_id, g, results,
                              chars_per_vision_token=chars_per_vision_token,
                              fidelity_floor=fidelity_floor, calibrated_at=calibrated_at)
        ref = prof.fidelity("reference")
        # rank: prefer clearing the floor; among those, denser cell = more chars/token.
        rank = (1 if ref >= fidelity_floor else 0, g.cols * g.rows)
        if best is None or rank > best[1] or (best is not None and rank == best[1]
                                              and ref > best[0].fidelity("reference")):
            best = (prof, rank)   # type: ignore[assignment]

    return best[0] if best else derive_profile(model_id, geometries[0], [],
                                                chars_per_vision_token=chars_per_vision_token,
                                                fidelity_floor=fidelity_floor)
