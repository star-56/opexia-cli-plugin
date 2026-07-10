"""OpexIA — direct HTTP emitter (Route 1). Any Python, only httpx required.

Install:  pip install httpx

POSTs a bare JSON ARRAY of flat span objects to $OPEXIA_INGEST_URL/v1/traces.
No OpenTelemetry, no collector. Ideal for edge functions, workers, or any place
a tracing SDK is unwelcome.

Wire contract (SKILL RULE 0/1):
  * flat dotted attribute keys, primitive values
  * compound fields (opexia.sources / opexia.decision) are json.dumps STRINGS
  * query_text / outcome_text are PLAIN strings
  * one unknown opexia.* key OR a nested-object value => the whole span dead-letters
"""
import json
import os
import time
import uuid
from typing import Optional

import httpx

INGEST_BASE = os.environ.get("OPEXIA_INGEST_URL", "https://ingest.opexia.dev").rstrip("/")
INGEST_URL = f"{INGEST_BASE}/v1/traces"
API_KEY = os.environ["OPEXIA_API_KEY"]
ORG_ID = os.environ["OPEXIA_ORG_ID"]
WORKSPACE_ID = os.environ["OPEXIA_WORKSPACE_ID"]
PROJECT_ID = os.environ.get("OPEXIA_PROJECT_ID", "default")

_FMT = "%Y-%m-%d %H:%M:%S.%f"


def new_trace_id() -> str:
    return uuid.uuid4().hex            # 32 hex chars


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]       # 16 hex chars


def build_span(
    *,
    trace_id: str,
    span_id: str,
    start_ns: int,
    end_ns: int,
    parent_span_id: Optional[str] = None,
    status_code: str = "OK",
    reasoning_role: Optional[str] = None,
    node_type: Optional[str] = None,
    end_user: Optional[str] = None,
    gen_ai_system: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    query_text: Optional[str] = None,      # earliest span (user question)
    outcome_text: Optional[str] = None,    # latest span (final answer)
    sources: Optional[dict] = None,        # {consulted, used, dropped, scores}
    decision: Optional[dict] = None,       # {rules_fired, scores, selected, alternatives}
    cost_usd: Optional[float] = None,
) -> dict:
    # --- required tenancy envelope (flat dotted, primitive values) ---
    attrs: dict = {
        "opexia.schema_version": "1.0",
        "opexia.org_id": ORG_ID,
        "opexia.workspace_id": WORKSPACE_ID,
        "opexia.project_id": PROJECT_ID,
        "opexia.trace_id": trace_id,     # keep identical to trace_id
    }
    if reasoning_role:
        attrs["opexia.reasoning_role"] = reasoning_role
    if node_type:
        attrs["opexia.node_type"] = node_type
    if end_user:
        attrs["opexia.end_user"] = end_user
    if query_text:
        attrs["opexia.query_text"] = query_text        # PLAIN string
    if outcome_text:
        attrs["opexia.outcome_text"] = outcome_text     # PLAIN string

    # gen_ai.* — standard OpenTelemetry GenAI names (NOT under opexia extra=forbid)
    if gen_ai_system:
        attrs["gen_ai.system"] = gen_ai_system
    if model:
        attrs["gen_ai.request.model"] = model
    if input_tokens:
        attrs["gen_ai.usage.input_tokens"] = int(input_tokens)
    if output_tokens:
        attrs["gen_ai.usage.output_tokens"] = int(output_tokens)

    # Compound fields go on the wire as JSON STRINGS (a dict here kills the span).
    if sources is not None:
        attrs["opexia.sources"] = json.dumps({
            "consulted": sources.get("consulted", []),   # list[str], not objects
            "used": sources.get("used", []),
            "dropped": sources.get("dropped", []),
            "scores": sources.get("scores", {}),
        })
    if decision is not None:
        attrs["opexia.decision"] = json.dumps({
            "rules_fired": decision.get("rules_fired", []),
            "scores": decision.get("scores", {}),
            "selected": decision.get("selected"),
            "alternatives": decision.get("alternatives", []),
        })
    # cost: flat dotted scalars, NOT a nested object.
    if cost_usd is not None:
        attrs["opexia.cost.usd"] = float(cost_usd)

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "start_time_unix_ns": int(start_ns),
        "end_time_unix_ns": int(end_ns),
        "status_code": status_code,        # "OK" | "ERROR"
        "attributes": attrs,
    }


def send(spans: list[dict]) -> httpx.Response:
    """POST a bare JSON array of spans. 202 is ACCEPTED, not proof of success —
    inspect the body for partialSuccess / rejected counts (see verify_span.py)."""
    r = httpx.post(
        INGEST_URL,
        headers={"x-opexia-api-key": API_KEY, "content-type": "application/json"},
        content=json.dumps(spans).encode("utf-8"),
        timeout=15.0,
    )
    return r


if __name__ == "__main__":
    # Minimal round trip: one span.
    tid, sid = new_trace_id(), new_span_id()
    now = time.time_ns()
    span = build_span(
        trace_id=tid, span_id=sid, start_ns=now - 5_000_000, end_ns=now,
        gen_ai_system="openai", model="gpt-4o", input_tokens=42, output_tokens=8,
        query_text="ping", outcome_text="pong",
    )
    resp = send([span])
    print(resp.status_code, resp.text[:400])
