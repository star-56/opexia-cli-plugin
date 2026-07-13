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
- **Installs** the dependency, pinned correctly (`--pre`, `opexia-trace>=0.1.0a13`).
- **Instruments** your code and enriches spans with the `opexia.*` intelligence
  attributes (sources, decision, reasoning, query/outcome text).
- **Renders prompts so they can be versioned** — on an LLM span, `opexia.query_text`
  *is the prompt*. The plugin knows to render it with role headers rather than
  space-joining the messages, which is the difference between one prompt with a
  version history and thousands of one-call rows in your Prompts page.
- **Writes** canonical env placeholders into `.env.example` (never real secrets).
- **Verifies** one span lands with zero dead-letters.

## Ship Check — the PR gate that comes with it

Once your prompts are traced, `opexia shipcheck` (ships in `opexia-trace`) checks a
prompt / model / config change **before it merges**. It makes **no LLM call** and
never re-runs your agent — it compares the candidate against the traces you already
sent and does arithmetic:

- token / cost-per-call / cost-per-month delta at your **measured** volume,
- **prompt-cache safety** — did the edit push per-call content into the cacheable
  prefix (which silently makes every call pay full price),
- structure regressions — examples removed, output format dropped,
- and a second, fully **local** gate that flags `CLAUDE.md`, `.claude/`,
  `.cursorrules` or an MCP config **shipping inside your production artifact**.

```bash
pip install "opexia-trace[shipcheck]"
opexia shipcheck            # exit 1 = the policy failed; 2 = the check could not run
```

Set `opexia.prompt_id` on your LLM spans (the plugin will offer to) so the gate can
match a changed prompt to its baseline exactly.

## Agent map & security audit — for the agentic projects this plugin instruments

The projects this plugin targets — apps with MCP servers, subagents, tools, and
hooks — are exactly the ones with an agent-security attack surface. `opexia audit`
(ships in `opexia-trace`, and runs automatically as a third gate of `opexia
shipcheck`) maps that whole system and audits it against the NSA's *Model Context
Protocol: Security Design Considerations*. It is **100% local and zero-egress: no
network call, no LLM, and nothing it finds ever leaves your machine** — a
vulnerability report must not itself disclose the vulnerability.

```bash
opexia audit --map agentmap.html    # writes a self-contained, offline HTML map
```

It draws your agents / servers / tools / hooks as an interactive map coloured by
trust zone (a **red edge is a private→internet path**), and flags: poisoned tool
descriptions (incl. **hidden-unicode** injection), cleartext credentials (shape
only, never the value), **unpinned `npx -y` / `uvx` servers** that run arbitrary
code on boot, shell-spawning servers, tool-name collisions, and **exfiltration
paths** where a secret can reach an external endpoint. Its headline is a committed
`.opexia/agentmap.lock`: a trusted server silently changing its tools — the
"rug-pull" — becomes a reviewable **diff in your PR**. When run inside `opexia
shipcheck`, the PR comment gets the verdict and finding *categories* only; the
evidence stays local, never posted.

## pxcore token compression — bundled MCP tools

The plugin bundles **pxcore** (pure stdlib, under `vendor/`) and registers an MCP server, so
four token-saving tools are available in Claude Code: `pxcore_read`, `pxcore_run`,
`pxcore_grep`, `pxcore_view`. They render **dense, reference** output (large file reads,
command output, logs) as an image the model reads with its **native vision** — cutting input
tokens — while keeping anything the model must reproduce verbatim (ids, paths, hashes, code
you edit) as text. Deterministic, **no LLM in the compression path**, and **nothing it
processes leaves the machine**.

Run `/opexia:compress` to set it up. **Two honest gates before it actually compresses** (until
then it safely returns text):

1. **Calibrate the active model.** The shipped Fable-5 profile is *provisional* — it images
   nothing until a real calibration run measures how reliably the model reads imaged text.
   Imaging is default-off per model and *earned* by calibration.
2. **Confirm image passthrough** — verify an image returned by an MCP tool reaches the model
   as image tokens, not flattened text (one-time check).

For bigger savings (the system prompt + history, which an MCP tool can't reach), run the
separate **`pxcore-proxy`** CLI and point Claude Code at it with `ANTHROPIC_BASE_URL` — see
`/opexia:compress proxy`. The proxy is a standalone CLI (needs `httpx`), not part of this
plugin's MCP bundle.

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
