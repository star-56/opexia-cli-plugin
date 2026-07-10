/**
 * OpexIA — verify one span lands with ZERO dead-letters (Node/TS).
 *
 * Run after instrumenting a JS/TS project:  node verify_span.mjs   (or ts-node)
 * POSTs a fully-formed span (explicit query/outcome text + a compound sources
 * field) straight to ingest and asserts it was accepted with nothing dropped.
 * Uses global fetch (Node 18+) — no dependency. Exit 0 = clean.
 *
 * Env: OPEXIA_INGEST_URL / OPEXIA_API_KEY / OPEXIA_ORG_ID / OPEXIA_WORKSPACE_ID
 *      [/ OPEXIA_PROJECT_ID].
 */
const base = (process.env.OPEXIA_INGEST_URL ?? "https://ingest.opexia.dev").replace(/\/$/, "");
const url = `${base}/v1/traces`;
const key = process.env.OPEXIA_API_KEY;
const org = process.env.OPEXIA_ORG_ID;
const ws = process.env.OPEXIA_WORKSPACE_ID;
const proj = process.env.OPEXIA_PROJECT_ID ?? "default";

const missing = [["OPEXIA_API_KEY", key], ["OPEXIA_ORG_ID", org], ["OPEXIA_WORKSPACE_ID", ws]]
  .filter(([, v]) => !v).map(([n]) => n);
if (missing.length) {
  console.error(`FAIL: missing env: ${missing.join(", ")}`);
  process.exit(2);
}

const hex = (n: number) =>
  Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join("");
const tid = hex(32);
const sid = hex(16);
const now = Date.now() * 1_000_000; // ms → ns

const span = {
  trace_id: tid,
  span_id: sid,
  parent_span_id: null,
  start_time_unix_ns: now - 5_000_000,
  end_time_unix_ns: now,
  status_code: "OK",
  attributes: {
    "opexia.schema_version": "1.0",
    "opexia.org_id": org,
    "opexia.workspace_id": ws,
    "opexia.project_id": proj,
    "opexia.trace_id": tid,
    "opexia.node_type": "agent",
    "opexia.query_text": "opexia verify: does this span land?",       // PLAIN string
    "opexia.outcome_text": "if you can read this in the dashboard, yes.",
    // compound field as a JSON STRING — exercises the #1 dead-letter trap
    "opexia.sources": JSON.stringify({
      consulted: ["https://example.com/a"], used: ["https://example.com/a"],
      dropped: [], scores: { "https://example.com/a": 0.9 },
    }),
    "gen_ai.system": "openai",
    "gen_ai.request.model": "gpt-4o",
    "gen_ai.usage.input_tokens": 12,
    "gen_ai.usage.output_tokens": 5,
  },
};

const main = async () => {
  let r: Response;
  try {
    r = await fetch(url, {
      method: "POST",
      headers: { "x-opexia-api-key": key!, "content-type": "application/json" },
      body: JSON.stringify([span]),
    });
  } catch (e) {
    console.error(`FAIL: could not reach ingest at ${url}: ${e}`);
    process.exit(2);
  }
  if (r.status === 415) {
    console.error("FAIL: 415 — ingest got protobuf; export OTLP/JSON (http/json).");
    process.exit(1);
  }
  const text = await r.text();
  if (r.status >= 400) {
    console.error(`FAIL: HTTP ${r.status}: ${text.slice(0, 400)}`);
    process.exit(1);
  }
  let body: any;
  try { body = JSON.parse(text); } catch {
    console.error(`FAIL: non-JSON ingest response: ${text.slice(0, 400)}`);
    process.exit(1);
  }
  const accepted = Number(body.accepted ?? 0);
  const rejected = Number(body.rejected ?? 0);
  if (rejected || accepted < 1) {
    console.error(`FAIL: span dead-lettered. accepted=${accepted} rejected=${rejected} ` +
      `reason=${body.partialSuccess?.errorMessage ?? JSON.stringify(body)}`);
    console.error("  -> check RULE 0/1: nested-object attribute? unknown opexia.* key? " +
      "compound field not JSON.stringify'd?");
    process.exit(1);
  }
  console.log(`OK: span accepted, 0 dead-letters. trace_id=${tid}`);
  console.log(`    accepted=${accepted} rejected=${rejected}`);
  console.log("    Open the OpexIA dashboard for this workspace and confirm the trace " +
    "appears with non-empty query/outcome text.");
  process.exit(0);
};
main();
