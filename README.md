# OpexIA Instrument — coding-CLI plugin

An agentic plugin that wires any project into **OpexIA observability** correctly.
Install it into your coding CLI (Claude Code), then run `/opexia:instrument` — it
detects your stack, picks the right integration route, writes the code and env,
and **verifies a span lands with zero dead-letters** before it calls the job done.

It is *packaged expertise*, not a code generator: the plugin gives your CLI the
OpexIA integration decision tree, the exact wire contract, and every silent
dead-letter trap, and the CLI's agent instruments your actual code from it.

## What it does

- **Detects** the stack: Python, Next.js, generic Node/TS, React (browser),
  React Native.
- **Picks and explains** the route:
  - Python greenfield → the `opexia-trace` SDK (`transport="direct"`).
  - Python already on OpenTelemetry → native OTLP/JSON.
  - Next.js / Node → native OTLP/JSON (there is **no** `@opexia/trace` npm
    package; JS uses standard OpenTelemetry JS + the bundled attribute kit).
  - Anything with an HTTP client → direct HTTP.
  - Browser React / React Native → **refuses the client path** and routes through
    a server, so your API key never ships in a client bundle.
- **Installs** the dependency, pinned correctly (`--pre`, `opexia-trace>=0.1.0a12`).
- **Instruments** your code and enriches spans with the `opexia.*` intelligence
  attributes (sources, decision, reasoning, query/outcome text).
- **Writes** canonical env placeholders into `.env.example` (never real secrets).
- **Verifies** one span lands with zero dead-letters.

## Install

**Local (from this monorepo):**
```
/plugin marketplace add ./tools/opexia-cli-plugin
/plugin install opexia@opexia
```

**Remote (point at the repo subdirectory):** add a marketplace entry with a
`git-subdir` source whose `path` is `tools/opexia-cli-plugin`, then
`/plugin install opexia@<your-marketplace>`. Validate any layout with
`claude plugin validate ./tools/opexia-cli-plugin`.

## Use

```
/opexia:instrument
/opexia:instrument use direct http
/opexia:instrument attribute per end user
```
Fill in the values the plugin writes into `.env.example`
(`OPEXIA_ORG_ID`, `OPEXIA_WORKSPACE_ID`, `OPEXIA_PROJECT_ID`, `OPEXIA_API_KEY`,
`OPEXIA_INGEST_URL`), then re-run the verify step.

## The one rule that breaks everything if ignored

OpenTelemetry span attributes hold only primitives. **Never send a nested
object/dict as an attribute value.** Compound OpexIA fields
(`opexia.sources`, `opexia.decision`, …) are sent as `json.dumps` /
`JSON.stringify` **strings**; `query_text`/`outcome_text` are plain strings. A
nested blob or an unknown `opexia.*` key silently dead-letters the whole span
(HTTP 202, then gone). The skill encodes this so the agent can't walk into it.

## License

Proprietary. Free to **install and use** to instrument your own applications for
OpexIA — but you may **not** redistribute, resell, sublicense, or fork it. See
[`LICENSE`](LICENSE). This is not open-source software.

## Layout

```
tools/opexia-cli-plugin/
  .claude-plugin/
    plugin.json           # manifest (name: opexia)
    marketplace.json      # git-installable marketplace entry
  skills/instrument/
    SKILL.md              # the decision procedure + wire contract + traps
    routes.md             # per-route deep reference
    templates/            # correct-by-construction starting points
      python_sdk_init.py
      python_direct_http.py
      nextjs_instrumentation.ts
      node_otlp_setup.ts
      opexia_attributes.ts
      verify_span.py
      verify_span.ts
      env.example.block
  README.md
```
