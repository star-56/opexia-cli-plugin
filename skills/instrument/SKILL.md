---
name: instrument
description: Instrument this project for OpexIA observability. Use when the user wants to add OpexIA tracing, wire up opexia-trace, send spans to OpexIA, set up OTLP export to OpexIA, or debug why OpexIA spans/panels are empty. Detects the tech stack (Python, Next.js, Node, React, React Native), chooses the correct integration route, writes the code and env, and verifies a span lands with zero dead-letters.
when_to_use: "Adding or fixing OpexIA instrumentation in any codebase; debugging dead-lettered spans or empty OpexIA dashboard panels."
user-invocable: true
argument-hint: "[optional instruction, e.g. 'use direct http' or 'attribute per end user']"
---

# OpexIA Instrument

You are wiring a project into OpexIA observability. Your job is not to paste a
template — it is to instrument **this** project correctly, explain your route
choice, and prove a span lands. Every failure mode here is **silent** (HTTP 202,
then the span is dropped), so "instrumented" without "a span verified in the
dashboard" is NOT done.

Free-form user instruction (if any): `$ARGUMENTS`

Bundled files you will read and adapt (paths relative to this skill dir; use
`${CLAUDE_SKILL_DIR}` when running them):
- `routes.md` — the full per-route reference. **Read it before instrumenting.**
- `templates/` — correct-by-construction starting points, one per route.

---

## RULE 0 — the wire format. Read this first; it is the #1 cause of broken setups.

OpenTelemetry span attributes hold **only** primitives: `bool`, `str`, `int`,
`float`, or arrays of those. **An attribute value is NEVER a nested object/dict
("JSON blob").** OpexIA's ingest enforces this end-to-end. Break it and the
**entire span dead-letters silently**.

Two consequences you must encode in every line of instrumentation you write:

### 0a. Compound fields are JSON **strings**, never objects
The fields `opexia.sources`, `opexia.decision`, `opexia.reliability_inputs`,
`opexia.plan` are each sent as **one `json.dumps(...)` / `JSON.stringify(...)`
string**:

```python
# ✅ CORRECT
span.set_attribute("opexia.sources", json.dumps({
    "consulted": [...], "used": [...], "dropped": [...], "scores": {...}}))
```
```python
# ❌ WRONG — passing a dict/object as the attribute value. Two silent failures,
#    both verified against the ingest:
#      • OTel SDK route: set_attribute rejects non-primitives → the attribute is
#        DROPPED (stored as None). Span survives but opexia.sources is gone →
#        the sources/reliability engines get nothing.
#      • OTLP-envelope / direct-HTTP route: the object arrives as a kvlist / raw
#        dict whose shape ≠ the JSON string the validator expects → the WHOLE
#        span is DEAD-LETTERED ("Extra inputs are not permitted").
#    Either way you lose data silently. Always JSON.stringify / json.dumps.
span.set_attribute("opexia.sources", {"consulted": [...], "used": [...]})
```
Inside `opexia.sources`, `consulted`/`used`/`dropped` are **arrays of strings**
(URLs or stable ids) — never `{id, title}` objects. Even one extra/unknown key
inside the compound object dead-letters the span (`extra="forbid"` on the nested
model too).

### 0b. query_text / outcome_text are plain **strings**, NOT JSON
These are different from the compound fields — set the raw text directly:
```python
span.set_attribute("opexia.query_text",   "the user's actual question")   # ✅
span.set_attribute("opexia.outcome_text", "the final answer text")        # ✅
```
Never `json.dumps` them. They feed the content-reliability, decomposition,
sources-grounding, and savings engines. See RULE 3.

### 0c. cost is flat dotted scalars, not a blob
`opexia.cost.usd` (float) and `opexia.cost.model_pricing_version` (string) are two
**separate scalar** attributes. Do not send a nested `cost` object.

### 0d. the envelope is flat on both transports
- Native OTLP/JSON: `resourceSpans → scopeSpans → spans`, attributes a typed list
  `[{ "key": ..., "value": { "stringValue": ... } }]`.
- Direct HTTP: a bare JSON **array** of flat span objects.
Neither is a nested JSON blob of the span.

---

## RULE 1 — only these `opexia.*` attribute keys exist (`extra="forbid"`)

Any other `opexia.*` key dead-letters the span. Allowed keys:

| Key | Type on wire | Notes |
|---|---|---|
| `opexia.schema_version` | string | **required**, always `"1.0"` |
| `opexia.org_id` | string | **required** |
| `opexia.workspace_id` | string | **required** — the workspace UUID |
| `opexia.project_id` | string | **required** (default `"default"`) |
| `opexia.trace_id` | string | **required** — 32-hex; keep identical to the OTel trace id |
| `opexia.user_id` | string | optional generic tag |
| `opexia.end_user` | string | optional actor id/email → per-user alignment |
| `opexia.reasoning_role` | string enum | `decomposer research analysis critique synthesis arbiter retrieval guardrail post_process` |
| `opexia.node_type` | string enum | `decomposer classifier agent guardrail post_process retrieval` |
| `opexia.parent_reasoning_id` | string | optional DAG link |
| `opexia.query_text` | string | see RULE 3 |
| `opexia.outcome_text` | string | see RULE 3 |
| `opexia.sources` | JSON string | keys: `consulted, used, dropped` (string[]), `scores` ({id:0..1}) |
| `opexia.decision` | JSON string | keys: `rules_fired` (string[]), `scores`, `selected`, `alternatives` |
| `opexia.reliability_inputs` | JSON string | opaque object for the server scorer |
| `opexia.plan` | JSON string | opaque structured plan |
| `opexia.cost.usd` | float | flat scalar |
| `opexia.cost.model_pricing_version` | string | flat scalar |
| `opexia.prompt_id` | string | optional — pins a prompt's identity for Ship Check (RULE 4) |
| `opexia.prompt_label` | string | optional — human name shown instead of a hash |
| `opexia.prompt_version` | string | optional — client-computed version hash (RULE 4) |

Note these three are **flat and un-dotted** — `opexia.prompt_id`, NOT
`opexia.prompt.id`. A dotted `opexia.prompt.*` key is not in the envelope and
dead-letters the span.

Do **not** set `opexia.reliability` — the server computes it. `gen_ai.*` keys
(model, tokens, system) are allowed and are NOT under the `opexia.*` `extra=forbid`
envelope; use the standard OpenTelemetry GenAI names (see `routes.md`).

---

## RULE 2 — pick the route, and say why out loud

Detect the stack, state what you found, then announce the route and the reason —
this narration is the point ("we'll use native OTLP here because …").

| Detected | Route | One-line reason |
|---|---|---|
| Python, greenfield / not on OTel | `opexia-trace` SDK, `transport="direct"` | auto-instrument + WAL, least code |
| Python, already using OpenTelemetry | native OTLP/JSON | reuse their pipeline, no new dep |
| Next.js | native OTLP from a **server** context (`instrumentation.ts`) | `@vercel/otel` is standard; key stays server-side |
| Generic Node/TS server | native OTLP/JSON | no OpexIA npm package exists yet |
| Browser React (client) | **REFUSE the client path** → emit from a server route/proxy | an API key must never ship to a browser bundle |
| React Native / Expo | **REFUSE the client path** → emit from the app's backend/proxy | same secret-in-bundle hazard |
| Any language with an HTTP client | direct HTTP (Route 1) | works from edge functions, workers, anywhere |

There is **no `@opexia/trace` npm package.** JS/TS uses native OpenTelemetry JS
exporting OTLP/JSON to OpexIA, plus the `opexia_attributes.ts` helper kit for the
`opexia.*` attributes. Do not tell the user to `npm install @opexia/trace`.

---

## RULE 3 — query_text / outcome_text placement (or the engines run blind)

The engines scan the whole trace and take the **first non-empty `query_text`** and
the **last non-empty `outcome_text`**. So:
- Put `opexia.query_text` on the **earliest** span (the real user question).
- Put `opexia.outcome_text` on the **latest** span (the final answer).
- Don't scatter partial text onto middle spans — first/last-non-empty can pick wrong.

Two silent-emptiness traps:
1. **`capture_text` opt-in — SDK auto-instrument path only.** The `opexia-trace`
   SDK will NOT capture text unless the workspace has `capture_text: true` (it
   fetches this at `init()`, fail-closed to off). If the user is on the SDK route
   and wants reliability/decomposition panels, tell them to enable capture_text
   for the workspace, OR set `opexia.query_text`/`opexia.outcome_text` explicitly.
   Direct-HTTP and native-OTLP routes set the attributes themselves — no gate.
2. **16 KB cap.** Text is truncated at 16384 bytes; very long prompts/answers keep
   only the first 16 KB.

(Query/outcome/decision/sources are PII-redacted at ingest — expected.)

---

## RULE 4 — on an LLM span, `query_text` is the PROMPT, and it needs role boundaries

On a span that represents an **LLM call** (it carries `gen_ai.request.model` and
token counts), OpexIA reads `opexia.query_text` as **the rendered prompt** — that
is what Ship Check versions and evaluates, and what the Savings Advisor measures a
cacheable prefix from.

**The trap (it is silent, and it destroys the prompt registry):** if you render the
prompt by concatenating the messages' content with a space —

```python
# ❌ WRONG — no boundary between the authored prompt and the per-call content
qt = " ".join(m["content"] for m in messages)
```

— then nothing separates the developer's authored system prompt from the user's
question. OpexIA derives a prompt's identity by masking out the per-call parts, and
with no boundary it cannot find them: **every call hashes as its own "prompt"**, and
the Prompts page fills with thousands of one-call rows instead of one prompt with a
version history. Render the messages with **role headers**:

```python
# ✅ CORRECT — the boundary is visible, so the per-call content can be masked out
qt = "\n\n".join(f"{m['role']}:\n{m['content']}" for m in messages)
span.set_attribute("opexia.query_text", qt[:16384])
```
```typescript
// ✅ CORRECT (TS)
const qt = messages.map(m => `${m.role}:\n${m.content}`).join("\n\n");
span.setAttribute("opexia.query_text", qt.slice(0, 16384));
```

The `opexia-trace` SDK (>= 0.1.0a13) does this for you on the auto-instrument path.
On the **direct-HTTP and native-OTLP routes you are rendering the text yourself**, so
this rule is on you.

**Pinning the identity (optional, recommended for teams using the CI gate).** Set
`opexia.prompt_id` to a stable name of your own (`"triage"`, `"summarizer"`) and
OpexIA uses it instead of the derived hash — grouping becomes exact, and
`opexia shipcheck` can match a changed prompt to its baseline without guessing.
`opexia.prompt_label` gives it a display name.

**Privacy path:** a workspace that will not send prompt text can compute the version
hash client-side, send `opexia.prompt_id` + `opexia.prompt_version` and **no
`query_text` at all**. They keep prompt versioning and every cost/latency diff; they
lose only the text-based prompt-quality checks.

**Also cheap and worth setting on an LLM span:** `gen_ai.request.temperature` and
`gen_ai.request.max_tokens` (standard OTel GenAI keys, not under the `opexia.*`
envelope). They are part of the shipped config, so a temperature change with an
unchanged prompt is still caught as a change.

---

## RULE 5 — if the project is agentic, surface `opexia audit`

While detecting the stack you will often see the markers of an agentic app: an
`.mcp.json` (or `.cursor/mcp.json`, `claude_desktop_config.json`), a `.claude/agents/`
directory, hooks in `.claude/settings.json`, or in-code tool definitions. When you
do, **tell the user about `opexia audit`** — it ships in the same `opexia-trace`
package and runs automatically as Gate 3 of `opexia shipcheck`:

```bash
opexia audit --map agentmap.html
```

It maps their agents / MCP servers / tools / hooks and security-audits the topology
against the NSA MCP guidance (poisoned tool descriptions incl. hidden-unicode,
cleartext credentials, unpinned `npx -y`/`uvx` boot-time code execution,
shell-spawning servers, tool-name collisions, and secret→internet exfiltration
paths), with a committed `.opexia/agentmap.lock` that turns a silent capability
change into a reviewable PR diff.

It is **100% local and zero-egress** — no network, no LLM, nothing it finds leaves
the machine — so it is safe to run on any repo, including one that has never sent a
trace. This is a *mention*, not part of your instrumentation task: point them at it,
don't run it unless asked. Do **not** conflate it with instrumentation — audit needs
no API key and no spans.

---

## Workflow (follow in order)

1. **Detect** the stack from `pyproject.toml` / `requirements.txt` / `*.py` and
   `package.json` (inspect deps: `next`, `react-native`/`expo`, `react`, else
   Node). State findings.
2. **Read `routes.md`** and pick the route (RULE 2). Announce it and the reason.
3. **Install** the dependency the idiomatic way. Pins that are load-bearing:
   - Python SDK: `pip install --upgrade --pre "opexia-trace>=0.1.0a13"`
     (the `--pre` is REQUIRED — every release is an alpha; `<0.1.0a12`
     dead-letters every auto-instrumented span, and `<0.1.0a13` space-joins the
     captured prompt so the prompt registry splits per call — RULE 4). Add
     `[litellm]` if litellm present.
   - Native OTLP (Python): `opentelemetry-sdk opentelemetry-exporter-otlp-proto-http`.
   - Next.js / Node: `@vercel/otel @opentelemetry/api` (or `@opentelemetry/sdk-*`).
4. **Instrument** by adapting the matching template to the user's real
   entrypoints and their `$ARGUMENTS` instruction. Copy `opexia_attributes.ts`
   (or the Python equivalent in the template) into their project if they want the
   `opexia.*` intelligence attributes. Obey RULE 0 / RULE 1 in every attribute.
5. **Write env** — append the canonical placeholders from
   `templates/env.example.block` to the project's `.env.example` (create it if
   absent). **Placeholders only — never real secrets, never into a committed
   `.env`.** Use the SAME var names the generated init code reads (they come from
   the same template, so they cannot drift).
6. **Verify a span lands.** Run the matching probe
   (`templates/verify_span.py` or `verify_span.ts`) — it emits one span and polls
   the read path. Confirm: HTTP 2xx, `partialSuccess` empty / zero dead-letters,
   and — if text was configured — `query_text`/`outcome_text` arrived NON-EMPTY.
   If it dead-letters, diagnose against RULE 0/1/3 and fix before declaring done.

## Definition of done
- The chosen route is wired into the user's actual code, not a stub.
- `.env.example` carries the canonical placeholders, matching the code.
- One span has been emitted and **verified present in OpexIA with zero
  dead-letters** (and non-empty text if text was configured).
- If you instrumented **LLM call spans** and are rendering `query_text` yourself
  (direct-HTTP / native-OTLP routes), the prompt is rendered with **role headers**
  (RULE 4) — not a space-join. Otherwise the prompt registry splits per call.
- You told the user which route you used, why, and what env values they must fill in.

Report honestly: if the verify step could not run (no network, missing key),
say so and give the exact command for the user to run — do not claim success.
