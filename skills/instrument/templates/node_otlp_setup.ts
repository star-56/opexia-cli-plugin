/**
 * OpexIA — generic Node/TS OTLP/JSON bootstrap (Route 0). Not Next.js.
 *
 * Import this module FIRST, before anything you want traced (`node -r ./otel.js`
 * or an import at the very top of your entrypoint).
 *
 * Install:
 *   npm i @opentelemetry/sdk-trace-node @opentelemetry/exporter-trace-otlp-http \
 *         @opentelemetry/resources @opentelemetry/semantic-conventions @opentelemetry/api
 *
 * MUST be the http/json exporter (OTLPTraceExporter from -otlp-http). Protobuf
 * export returns 415 from OpexIA ingest.
 */
import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";

const base = (process.env.OPEXIA_INGEST_URL ?? "https://ingest.opexia.dev").replace(/\/$/, "");

const exporter = new OTLPTraceExporter({
  url: `${base}/v1/traces`,
  headers: { "x-opexia-api-key": process.env.OPEXIA_API_KEY ?? "" },
});

const provider = new NodeTracerProvider({
  resource: resourceFromAttributes({
    // service.name → opexia.project_id fallback at ingest.
    [ATTR_SERVICE_NAME]: process.env.OPEXIA_PROJECT_ID || "default",
  }),
  spanProcessors: [new BatchSpanProcessor(exporter)],
});
provider.register();

// Flush on shutdown so the last batch isn't lost.
process.on("SIGTERM", () => provider.shutdown().catch(() => {}));

// Then enrich spans via ./opexia_attributes.ts (initOpexia + withOpexiaTrace).
// RULE 0: compound fields are JSON strings; query_text/outcome_text plain strings.
