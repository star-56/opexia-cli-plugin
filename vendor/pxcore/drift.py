# pxcore/drift.py — reading-fidelity drift, purpose-built (NOT lifted from observability).
#
# The signal is one thing and one thing only: the rolling pass-rate of fidelity probes per
# (model_id, fidelity_class) over time. When a provider silently updates a model behind the
# same id, or a new version reads dense text worse, that pass-rate falls — and this module
# AUTO-DEMOTES the affected class to text and flags the profile for re-calibration, until it
# re-clears the floor.
#
# Its own signal, its own store, its own thresholds. It imports no other subsystem.
from __future__ import annotations

import json
import os
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple


class DriftMonitor:
    def __init__(self, window: int = 50, store: Optional[str] = None):
        self.window = window
        self.store = store or os.path.join(os.path.expanduser("~"), ".pxcore", "drift.jsonl")
        # (model_id, class) -> recent pass/fail booleans
        self._recent: Dict[Tuple[str, str], Deque[bool]] = {}

    def observe(self, model_id: str, fidelity_class: str, passed: bool,
                ts: Optional[float] = None) -> None:
        key = (model_id, fidelity_class)
        dq = self._recent.setdefault(key, deque(maxlen=self.window))
        dq.append(passed)
        self._append(model_id, fidelity_class, passed, ts)

    def pass_rate(self, model_id: str, fidelity_class: str) -> Optional[float]:
        dq = self._recent.get((model_id, fidelity_class))
        if not dq:
            return None
        return sum(dq) / len(dq)

    def is_demoted(self, model_id: str, fidelity_class: str, floor: float,
                   *, min_samples: int = 10) -> bool:
        """True → force this class to TEXT regardless of the stored profile. A model that USED
        to pass but is now failing live is more trustworthy than a stale profile that says it
        passes. Requires min_samples so one bad read doesn't nuke a good model."""
        dq = self._recent.get((model_id, fidelity_class))
        if not dq or len(dq) < min_samples:
            return False
        return (sum(dq) / len(dq)) < floor

    def _append(self, model_id: str, cls: str, passed: bool, ts: Optional[float]) -> None:
        try:
            d = os.path.dirname(self.store)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.store, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts if ts is not None else time.time(),
                                    "model_id": model_id, "class": cls,
                                    "passed": passed}) + "\n")
        except OSError:
            pass       # drift logging must never break serving
