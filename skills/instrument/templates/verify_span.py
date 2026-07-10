"""OpexIA — verify one span lands with ZERO dead-letters (Python).

Run this after instrumenting. It POSTs a fully-formed test span (explicit
query_text/outcome_text + a compound sources field, so it exercises the wire
contract) and asserts the ingest ACCEPTED it and dead-lettered nothing.

Because every OpexIA failure mode is silent (HTTP 202, then dropped), this is
the only honest proof that instrumentation works. Exit 0 = clean.

    python verify_span.py

Needs: httpx, and env OPEXIA_INGEST_URL / OPEXIA_API_KEY / OPEXIA_ORG_ID /
OPEXIA_WORKSPACE_ID [/ OPEXIA_PROJECT_ID].
"""
import json
import os
import sys
import time
import uuid

import httpx

base = os.environ.get("OPEXIA_INGEST_URL", "https://ingest.opexia.dev").rstrip("/")
url = f"{base}/v1/traces"
key = os.environ.get("OPEXIA_API_KEY")
org = os.environ.get("OPEXIA_ORG_ID")
ws = os.environ.get("OPEXIA_WORKSPACE_ID")
proj = os.environ.get("OPEXIA_PROJECT_ID", "default")

missing = [n for n, v in (("OPEXIA_API_KEY", key), ("OPEXIA_ORG_ID", org),
                          ("OPEXIA_WORKSPACE_ID", ws)) if not v]
if missing:
    print(f"FAIL: missing env: {', '.join(missing)}")
    sys.exit(2)

tid = uuid.uuid4().hex
sid = uuid.uuid4().hex[:16]
now = time.time_ns()

span = {
    "trace_id": tid,
    "span_id": sid,
    "parent_span_id": None,
    "start_time_unix_ns": now - 5_000_000,
    "end_time_unix_ns": now,
    "status_code": "OK",
    "attributes": {
        "opexia.schema_version": "1.0",
        "opexia.org_id": org,
        "opexia.workspace_id": ws,
        "opexia.project_id": proj,
        "opexia.trace_id": tid,
        "opexia.node_type": "agent",
        "opexia.query_text": "opexia verify: does this span land?",   # PLAIN string
        "opexia.outcome_text": "if you can read this in the dashboard, yes.",
        # compound field as a JSON STRING — exercises the #1 dead-letter trap
        "opexia.sources": json.dumps({
            "consulted": ["https://example.com/a"], "used": ["https://example.com/a"],
            "dropped": [], "scores": {"https://example.com/a": 0.9}}),
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.usage.input_tokens": 12,
        "gen_ai.usage.output_tokens": 5,
    },
}

try:
    r = httpx.post(url, headers={"x-opexia-api-key": key,
                                 "content-type": "application/json"},
                   content=json.dumps([span]).encode("utf-8"), timeout=20.0)
except Exception as e:
    print(f"FAIL: could not reach ingest at {url}: {type(e).__name__}: {e}")
    sys.exit(2)

if r.status_code == 415:
    print("FAIL: 415 — ingest got protobuf; you must export OTLP/JSON (http/json).")
    sys.exit(1)
if r.status_code >= 400:
    print(f"FAIL: HTTP {r.status_code}: {r.text[:400]}")
    sys.exit(1)

try:
    body = r.json()
except Exception:
    print(f"FAIL: non-JSON ingest response: {r.text[:400]}")
    sys.exit(1)

accepted = int(body.get("accepted", 0))
rejected = int(body.get("rejected", 0))
if rejected or accepted < 1:
    # partialSuccess.errorMessage carries reason CODES (never your data).
    ps = body.get("partialSuccess", {})
    print(f"FAIL: span dead-lettered. accepted={accepted} rejected={rejected} "
          f"reason={ps.get('errorMessage', body)}")
    print("  -> check SKILL RULE 0/1: nested-object attribute? unknown opexia.* key? "
          "compound field not JSON.stringify'd?")
    sys.exit(1)

print(f"OK: span accepted, 0 dead-letters. trace_id={tid}")
print(f"    accepted={accepted} rejected={rejected}")
print("    Open the OpexIA dashboard for this workspace and confirm the trace "
      "appears with non-empty query/outcome text.")
sys.exit(0)
