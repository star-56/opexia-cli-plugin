/**
 * OpexIA attribute kit (TypeScript / OpenTelemetry JS)
 * ====================================================
 * There is NO @opexia/trace npm package. JS/TS instruments via native
 * OpenTelemetry JS exporting OTLP/JSON to OpexIA, and these helpers set the
 * opexia.* attributes correctly.
 *
 * WIRE CONTRACT (SKILL RULE 0 — violations are dead-lettered silently at ingest):
 *   - Compound fields are JSON STRINGS: setAttribute("opexia.sources", JSON.stringify({...}))
 *     A nested object becomes an OTLP kvlistValue and kills the whole span.
 *   - consulted/used/dropped are string[] (URLs or stable ids), NOT {id,title} objects.
 *   - query_text/outcome_text are PLAIN strings (never JSON.stringify).
 *   - Only the documented opexia.* keys exist (extra="forbid"); any other kills the span.
 *
 * Requires: @opentelemetry/api (present in any OTel-instrumented app).
 */
import { trace, context, Span, SpanStatusCode, Tracer } from "@opentelemetry/api";

// Server-validated enums — anything else fails validation.
export type ReasoningRole =
  | "decomposer" | "research" | "analysis" | "critique"
  | "synthesis" | "arbiter" | "retrieval" | "guardrail" | "post_process";
export type NodeType =
  | "decomposer" | "classifier" | "agent" | "guardrail"
  | "post_process" | "retrieval";

export interface OpexiaEnvelope {
  orgId: string;
  workspaceId: string;   // workspace UUID the dashboard reads
  projectId: string;
  userId?: string;
}

/** Required tenancy envelope — set on EVERY span. */
export function setOpexiaEnvelope(span: Span, env: OpexiaEnvelope): void {
  span.setAttribute("opexia.schema_version", "1.0");
  span.setAttribute("opexia.org_id", env.orgId);
  span.setAttribute("opexia.workspace_id", env.workspaceId);
  span.setAttribute("opexia.project_id", env.projectId);
  if (env.userId) span.setAttribute("opexia.user_id", env.userId);
  // Keep opexia.trace_id identical to the OTel trace id.
  span.setAttribute("opexia.trace_id", span.spanContext().traceId);
}

/** Optional per-user actor attribution (drives per-user alignment flagging). */
export function setOpexiaEndUser(span: Span, endUser: string): void {
  if (endUser) span.setAttribute("opexia.end_user", endUser);
}

export interface OpexiaSources {
  consulted?: string[];   // string ids/URLs, NOT objects
  used?: string[];        // subset actually cited → drives source_authority
  dropped?: string[];
  scores?: Record<string, number>;  // 0..1 per id
}

/** opexia.sources as a JSON STRING with ONLY the 4 allowed keys. */
export function setOpexiaSources(span: Span, src: OpexiaSources): void {
  span.setAttribute("opexia.sources", JSON.stringify({
    consulted: src.consulted ?? [],
    used: src.used ?? [],
    dropped: src.dropped ?? [],
    scores: src.scores ?? {},
  }));
}

export interface OpexiaDecision {
  selected?: string;
  rulesFired?: string[];
  scores?: Record<string, number>;
  alternatives?: Record<string, unknown>[];
}

/** opexia.decision as a JSON STRING with ONLY the 4 allowed keys. */
export function setOpexiaDecision(span: Span, dec: OpexiaDecision): void {
  span.setAttribute("opexia.decision", JSON.stringify({
    rules_fired: dec.rulesFired ?? [],
    scores: dec.scores ?? {},
    selected: dec.selected ?? null,
    alternatives: dec.alternatives ?? [],
  }));
}

export function setOpexiaReasoning(
  span: Span,
  opts: { role?: ReasoningRole; nodeType?: NodeType; parentReasoningId?: string },
): void {
  if (opts.role) span.setAttribute("opexia.reasoning_role", opts.role);
  if (opts.nodeType) span.setAttribute("opexia.node_type", opts.nodeType);
  if (opts.parentReasoningId)
    span.setAttribute("opexia.parent_reasoning_id", opts.parentReasoningId);
}

/**
 * Capture the user query + final answer — PLAIN strings, never JSON.
 * Put `query` on the EARLIEST span and `outcome` on the LATEST span of the trace
 * (engines take first-non-empty query / last-non-empty outcome). ~16 KB cap.
 */
export function setOpexiaText(span: Span, text: { query?: string; outcome?: string }): void {
  if (text.query) span.setAttribute("opexia.query_text", text.query);
  if (text.outcome) span.setAttribute("opexia.outcome_text", text.outcome);
}

/** gen_ai.* — standard OTel GenAI semconv. Cost is inferred server-side if omitted. */
export function setGenAiUsage(
  span: Span,
  usage: {
    system?: string; model?: string; operation?: string;
    inputTokens?: number; outputTokens?: number; finishReason?: string;
    costUsd?: number; pricingVersion?: string;
  },
): void {
  if (usage.system) span.setAttribute("gen_ai.system", usage.system);
  if (usage.model) span.setAttribute("gen_ai.request.model", usage.model);
  if (usage.operation) span.setAttribute("gen_ai.operation.name", usage.operation);
  if (usage.inputTokens != null) span.setAttribute("gen_ai.usage.input_tokens", usage.inputTokens);
  if (usage.outputTokens != null) span.setAttribute("gen_ai.usage.output_tokens", usage.outputTokens);
  if (usage.finishReason) span.setAttribute("gen_ai.response.finish_reason", usage.finishReason);
  if (usage.costUsd != null) span.setAttribute("opexia.cost.usd", usage.costUsd);          // flat scalar
  if (usage.pricingVersion) span.setAttribute("opexia.cost.model_pricing_version", usage.pricingVersion);
}

// --- One-trace-per-request wrapper ------------------------------------------
let _tracer: Tracer | null = null;
let _env: OpexiaEnvelope | null = null;

export function initOpexia(env: OpexiaEnvelope, tracerName = "opexia"): void {
  _env = env;
  _tracer = trace.getTracer(tracerName);
}

/** Wrap one logical request (= one trace); root span gets the envelope. */
export async function withOpexiaTrace<T>(
  name: string,
  fn: (span: Span) => Promise<T>,
  opts?: { role?: ReasoningRole; nodeType?: NodeType },
): Promise<T> {
  if (!_tracer || !_env) throw new Error("call initOpexia() first");
  const tracer = _tracer, env = _env;
  return tracer.startActiveSpan(name, async (span) => {
    setOpexiaEnvelope(span, env);
    if (opts) setOpexiaReasoning(span, opts);
    try {
      const out = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return out;
    } catch (err) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
      throw err;
    } finally {
      span.end();
    }
  });
}

/** Child span inside the current trace (envelope auto-applied). */
export function startOpexiaSpan(name: string): Span {
  if (!_tracer || !_env) throw new Error("call initOpexia() first");
  const span = _tracer.startSpan(name, undefined, context.active());
  setOpexiaEnvelope(span, _env);
  return span;
}
