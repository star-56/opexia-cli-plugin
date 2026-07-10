/**
 * OpexIA — Next.js instrumentation (Route 0, native OTLP/JSON, SERVER ONLY).
 *
 * Place this file at the PROJECT ROOT as `instrumentation.ts` (Next.js loads it
 * automatically on the server). Never instrument from a client component — the
 * API key must never reach the browser bundle.
 *
 * Install:  npm i @vercel/otel @opentelemetry/api
 *
 * Env (see env.example.block). MUST be http/json — protobuf export returns 415:
 *   OPEXIA_INGEST_URL=https://ingest.opexia.dev
 *   OPEXIA_API_KEY=opx_live_…            (server-only secret)
 *
 * After this registers the exporter, enrich spans with the opexia.* attributes
 * using ./opexia_attributes.ts (copy it into your project). RULE 0 applies:
 * compound fields are JSON strings; query_text/outcome_text are plain strings.
 */
import { registerOTel, OTLPHttpJsonTraceExporter } from "@vercel/otel";

export function register(): void {
  const base = (process.env.OPEXIA_INGEST_URL ?? "https://ingest.opexia.dev").replace(/\/$/, "");
  registerOTel({
    // service.name becomes opexia.project_id when a project id header is absent.
    serviceName: process.env.OPEXIA_PROJECT_ID || "default",
    traceExporter: new OTLPHttpJsonTraceExporter({
      url: `${base}/v1/traces`,
      headers: {
        "x-opexia-api-key": process.env.OPEXIA_API_KEY ?? "",
      },
    }),
  });
}

/**
 * USAGE in a route handler / server action (NOT a client component):
 *
 *   // app/api/ask/route.ts
 *   import { initOpexia, withOpexiaTrace, setOpexiaText, setGenAiUsage }
 *     from "@/lib/opexia_attributes";
 *
 *   initOpexia({
 *     orgId: process.env.OPEXIA_ORG_ID!,
 *     workspaceId: process.env.OPEXIA_WORKSPACE_ID!,
 *     projectId: process.env.OPEXIA_PROJECT_ID ?? "default",
 *   });
 *
 *   export async function POST(req: Request) {
 *     const { question } = await req.json();
 *     const answer = await withOpexiaTrace("chat.turn", async (span) => {
 *       setOpexiaText(span, { query: question });      // earliest span
 *       const res = await callYourLLM(question);
 *       setGenAiUsage(span, {
 *         system: "openai", model: "gpt-4o",
 *         inputTokens: res.usage.prompt_tokens,
 *         outputTokens: res.usage.completion_tokens,
 *       });
 *       setOpexiaText(span, { outcome: res.text });     // final answer on same/last span
 *       return res.text;
 *     }, { nodeType: "agent" });
 *     return Response.json({ answer });
 *   }
 */
