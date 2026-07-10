# OpexIA integration routes — full reference

Three routes. All land at the same ingest host; they differ in how spans are
produced and shipped. Read RULE 0/1 in `SKILL.md` first — the wire contract is
identical across all three.

## Endpoints & the envelope backfill

- **Ingest host:** `OPEXIA_INGEST_URL` (e.g. `https://ingest.opexia.dev`).
- **Path:** `/v1/traces` (a registered alias of `/v1/otlp/traces` — both work).
- **Auth:** header `x-opexia-api-key: <OPEXIA_API_KEY>` (`opx_live_…` / `opx_test_…`).
- The ingest **backfills the tenancy envelope from the API key** when omitted:
  a stock OTel exporter with the three OTEL env vars and ZERO `opexia.*`
  attributes still ingests — you get spans, latency, errors, and fleet topology.
  Add the `opexia.*` attributes (RULE 1) to light up the intelligence engines.
- `opexia.project_id` resolves as: header `x-opexia-project-id` → Resource
  `service.name` → `"default"`.

## Route 0 — native OTLP/JSON (your existing / a fresh OTel SDK)

Best when the app already traces, and the ONLY option for JS/TS today.

**Must be OTLP/JSON, not protobuf.** Protobuf export → `415`. Set:
```
OTEL_EXPORTER_OTLP_ENDPOINT=$OPEXIA_INGEST_URL
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json
OTEL_EXPORTER_OTLP_HEADERS=x-opexia-api-key=$OPEXIA_API_KEY
```
The exporter appends `/v1/traces`. Add `opexia.*` attributes on the spans you
already create (Python: `span.set_attribute(...)`; TS: the `opexia_attributes.ts`
kit). Resource attributes inherit to every span, but only the envelope keys
(`service.name`, `gen_ai.*`, `agent.name`, and the five `opexia.*` envelope
fields); any other `opexia.*` Resource attribute is dropped, not inherited — so
set per-span attributes on the span, not the Resource.

- **Python native OTLP:** `templates/node_otlp_setup.ts` has the TS shape; for
  Python use the standard `TracerProvider` + `OTLPSpanExporter` (http/json) and
  set the three env vars above. Prefer the SDK (Route 2) for greenfield Python.
- **Next.js:** `templates/nextjs_instrumentation.ts` — `@vercel/otel` `register()`
  in `instrumentation.ts`, **server side only**.
- **Generic Node/TS:** `templates/node_otlp_setup.ts`.

## Route 1 — direct HTTP (any language, no OTel dependency)

POST a bare JSON **array** of flat span objects to `/v1/traces`. No OTel, no
collector. The right choice inside a Supabase Edge Function, a Cloudflare Worker,
or any bundle where a tracing SDK is unwelcome. This is the route verified
end-to-end in the OpexIA docs.

- **Python:** `templates/python_direct_http.py` (needs only `httpx`).
- Each span is a flat dict: `trace_id`, `span_id`, `parent_span_id`,
  `start_time_unix_ns`/`end_time_unix_ns` (ints), plus the flat dotted attributes
  of RULE 1. Compound fields are JSON strings; text fields are plain strings.

## Route 2 — the `opexia-trace` Python SDK (greenfield Python)

Best ergonomics: auto-instrument, `@observe`, durable WAL.
```
pip install --upgrade --pre "opexia-trace>=0.1.0a12"
```
`--pre` is required (every release is an alpha). `<0.1.0a12` dead-letters every
auto-instrumented span — do not pin below it.

```python
from opexia.trace import init
init(
    org_id=..., workspace_id=..., project_id=...,
    backend_url=OPEXIA_INGEST_URL,     # the ingest host
    api_key=OPEXIA_API_KEY,
    transport="direct",                # POST straight to ingest; no collector/gRPC
    auto_instrument=True,
)
```
- `transport="direct"` (or env `OPEXIA_TRANSPORT=direct`) ships spans straight to
  `backend_url`. The default `transport="collector"` sends OTLP/gRPC to
  `collector_endpoint` (`http://localhost:4317`) and needs a collector configured
  with `encoding: json` on its `otlphttp` exporter — only pick it if the user
  already runs a collector.
- `fail_open=True` degrades gracefully if init/exporter/WAL fails (won't crash
  app startup). `sampler_rate` controls sampling.
- **capture_text:** auto-instrument captures `query_text`/`outcome_text` ONLY when
  the workspace has `capture_text: true` (fetched at init, fail-closed). See
  SKILL RULE 3. `template/python_sdk_init.py` is the adaptable starting point.

`gen_ai.*` attribute names (standard OpenTelemetry GenAI semconv), for cost +
tokens on native/direct routes:
- `gen_ai.system` (e.g. `openai`, `anthropic`)
- `gen_ai.request.model`
- `gen_ai.operation.name` (e.g. `chat`)
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.usage.cache_read_input_tokens` / `cached_tokens` (cache split)
- `gen_ai.response.finish_reason`
If you omit `opexia.cost.usd`, the backend infers cost from model + tokens.

## Refused paths (secrets)

- **Browser React:** never emit directly from the browser — the API key would ship
  in the client bundle. Emit from a server route handler / API route / proxy that
  holds the key, and forward the browser's query/answer to it.
- **React Native / Expo:** same — instrument the app's backend or a thin server
  proxy, not the device app.
