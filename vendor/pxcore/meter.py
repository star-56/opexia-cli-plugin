# pxcore/meter.py — savings accounting. Deterministic; no network, no model call.
#
# Appends one row per decision so savings are MEASURED from real traffic, not asserted. This
# is also the feed that lets calibration re-derive a profile from production (a model's true
# imaged density is whatever the events log says it was).
from __future__ import annotations

import json
import os
import time
from typing import Optional


class Meter:
    def __init__(self, sink: Optional[str] = None):
        # default local, per-user; never leaves the machine.
        self.sink = sink or os.path.join(os.path.expanduser("~"), ".pxcore", "events.jsonl")

    def record(self, *, model_id: str, decision: str, text_tokens: int,
               image_tokens: int, saved: int, reason: str = "",
               ts: Optional[float] = None) -> None:
        row = {
            "ts": ts if ts is not None else time.time(),
            "model_id": model_id,
            "decision": decision,           # "image" | "text"
            "text_tokens": text_tokens,
            "image_tokens": image_tokens,
            "saved_tokens": saved,
            "reason": reason,
        }
        try:
            d = os.path.dirname(self.sink)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.sink, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except OSError:
            # metering must never break a decision. Drop the row, keep serving.
            pass
