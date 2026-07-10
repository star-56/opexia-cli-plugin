"""OpexIA — opexia-trace SDK bootstrap (Route 2, greenfield Python).

Install:  pip install --upgrade --pre "opexia-trace>=0.1.0a12"
          # --pre is REQUIRED (every release is an alpha). <0.1.0a12 dead-letters
          # every auto-instrumented span — do not pin below it.

Call init() ONCE, as early as possible in process startup (before the LLM
clients you want auto-instrumented are used). The agent adapting this template
should place the call in the real entrypoint (e.g. main.py / app factory).
"""
import os

from opexia.trace import init


def init_opexia() -> None:
    init(
        org_id=os.environ["OPEXIA_ORG_ID"],
        workspace_id=os.environ["OPEXIA_WORKSPACE_ID"],
        project_id=os.environ.get("OPEXIA_PROJECT_ID", "default"),
        # The ingest host. For transport="direct" spans POST straight here.
        backend_url=os.environ["OPEXIA_INGEST_URL"],
        api_key=os.environ["OPEXIA_API_KEY"],
        # "direct" = no collector, no gRPC. Or set OPEXIA_TRANSPORT=direct in env.
        transport=os.environ.get("OPEXIA_TRANSPORT", "direct"),
        auto_instrument=True,
        # Degrade gracefully instead of crashing app startup if the exporter or
        # WAL can't initialise. Flip to False if you want init failures to raise.
        fail_open=True,
    )


# ---------------------------------------------------------------------------
# Enriching spans with the opexia.* intelligence attributes (optional).
#
# Auto-instrument alone gives you spans, latency, errors, cost, and fleet
# topology. To light up the reasoning/reliability/sources engines, attach the
# opexia.* attributes to the ACTIVE span. Every value obeys SKILL RULE 0:
#   - compound fields (sources/decision) are json.dumps STRINGS, never dicts
#   - query_text/outcome_text are PLAIN strings, never json.dumps
# ---------------------------------------------------------------------------
import json

from opentelemetry import trace as _ot_trace


def annotate_current_span(
    *,
    query_text: str | None = None,      # put on the EARLIEST span (user question)
    outcome_text: str | None = None,    # put on the LATEST span (final answer)
    reasoning_role: str | None = None,  # decomposer|research|analysis|critique|
                                        # synthesis|arbiter|retrieval|guardrail|post_process
    node_type: str | None = None,       # decomposer|classifier|agent|guardrail|
                                        # post_process|retrieval
    end_user: str | None = None,        # employee id/email → per-user alignment
    sources: dict | None = None,        # {consulted:[str], used:[str], dropped:[str], scores:{id:0..1}}
    decision: dict | None = None,       # {rules_fired:[str], scores:{}, selected:str, alternatives:[]}
) -> None:
    span = _ot_trace.get_current_span()
    if span is None:
        return
    if query_text:
        span.set_attribute("opexia.query_text", query_text)        # PLAIN string
    if outcome_text:
        span.set_attribute("opexia.outcome_text", outcome_text)    # PLAIN string
    if reasoning_role:
        span.set_attribute("opexia.reasoning_role", reasoning_role)
    if node_type:
        span.set_attribute("opexia.node_type", node_type)
    if end_user:
        span.set_attribute("opexia.end_user", end_user)
    if sources is not None:
        # JSON STRING — a dict here would dead-letter the whole span.
        span.set_attribute("opexia.sources", json.dumps({
            "consulted": sources.get("consulted", []),   # list[str], NOT objects
            "used": sources.get("used", []),
            "dropped": sources.get("dropped", []),
            "scores": sources.get("scores", {}),
        }))
    if decision is not None:
        span.set_attribute("opexia.decision", json.dumps({
            "rules_fired": decision.get("rules_fired", []),
            "scores": decision.get("scores", {}),
            "selected": decision.get("selected"),
            "alternatives": decision.get("alternatives", []),
        }))
