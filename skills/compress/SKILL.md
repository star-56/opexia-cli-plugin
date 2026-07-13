---
name: compress
description: Set up and use pxcore token compression in Claude Code — render bulky, dense, reference tool-output as images the model reads with native vision, cutting input tokens while keeping exact content (ids, paths, hashes, code you edit) as text. Use when the user wants to reduce token cost / context bloat, calibrate pxcore for their model, or understand why compression is or isn't active.
when_to_use: "Reducing Claude Code token/context cost via image-as-context; calibrating pxcore for the active model; enabling/verifying pxcore compression."
user-invocable: true
argument-hint: "[calibrate | status | proxy]"
---

# pxcore compression

pxcore cuts input tokens by rendering **dense, reference** tool output (large file reads,
command output, logs) as an image the model reads with its **native vision** — while keeping
anything the model must reproduce verbatim (ids, paths, hashes, code you will edit) as text.
Deterministic; **no LLM is ever called to compress or score**; nothing it processes leaves the
machine.

Free-form user instruction (if any): `$ARGUMENTS`

## What is already wired

This plugin bundles pxcore (pure stdlib) and registers an MCP server, so four tools are
available now:

- `pxcore_read(path)` — read a file, returned token-efficiently.
- `pxcore_run(command)` — run a command, output returned token-efficiently.
- `pxcore_grep(pattern, path)` — search, results returned token-efficiently.
- `pxcore_view(text, exact?)` — image a block you already hold; `exact:true` forces text.

**Adoption note:** the model defaults to native `Read`/`Bash`/`Grep`. To get the benefit,
prefer the `pxcore_*` tools for **large, read-only reference** work (big logs, generated
files, command dumps) — never for a file you are about to edit.

## Two gates before it actually compresses — be honest about these

Out of the box pxcore returns **text** (safe, no compression) until BOTH are cleared. Do not
tell the user they are saving tokens until they are.

### Gate 1 — calibrate the active model (`/opexia:compress calibrate`)

The shipped `claude-fable-5` profile is **provisional**: its fidelity scores are 0, so it
images **nothing** until a real calibration run measures how well *this* model reads imaged
text. A score is never asserted without a measurement.

To calibrate, run the battery against the model that will consume the images. In this
environment the running agent *is* that model, so it can calibrate itself:

1. Generate the probe set with pxcore's battery (novel arithmetic, verbatim 12-char hex,
   state-tracking) at each candidate geometry.
2. For each probe image, have the model read it and answer; score exact-match (no LLM judge).
3. Write the local profile with the measured fidelity scores + the densest geometry that
   clears the floor. `pxcore` then images reference content **only** where the model proved
   it reads it back reliably; exact content always stays text.

Run it from the bundled package:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/vendor" python -c "from pxcore.calibration import battery; print('probes:', len(battery.build_probes(battery._GEOMETRIES[0])))"
```

The adapter/skill supplies the model's answers; the core defines probes and scores them. A
model that fails the battery gets a profile that images nothing — which is correct, not a bug.

### Gate 2 — confirm image passthrough (one-time, ~5 min)

pxcore assumes an image returned by an MCP tool reaches the model as **image tokens**, not
flattened text. This is strongly implied but not yet verified in-house. Before trusting the
savings: call `pxcore_view` on a distinctive block, confirm the model can describe the image
content, and confirm the request's usage shows image tokens (not text). If it flattens to
text, compression via MCP is not delivering — stop and report it.

## Bigger savings: the proxy (separate CLI, optional)

An MCP tool can only shrink **tool results**. The **system prompt + history** (usually the
larger sink) can only be reached in-path. For that, run the pxcore **proxy** (a separate CLI,
needs `httpx`) and point Claude Code at it:

```bash
pip install "pxcore[proxy]"          # or run from the pxcore repo
pxcore-proxy                          # 127.0.0.1:8788 -> api.anthropic.com
# then launch Claude Code with:  ANTHROPIC_BASE_URL=http://127.0.0.1:8788
```

The proxy images the system prompt + history + tool results cache-safely, never touches the
active turn, and obeys the same calibration (images nothing until the model is calibrated).

## Safety spine (always true)

- Exact content (ids, paths, hashes) and anything you will edit **stays text** — a misread
  glyph must never become a wrong edit.
- Imaging is **default-off per model** and earned only by calibration; drift auto-demotes a
  model back to text if it regresses.
- **Zero egress**: pxcore makes no network call and nothing it processes leaves the machine.

## Definition of done (for a setup request)

- The `pxcore` MCP server is listed in `/mcp` and its tools respond.
- The active model has a **calibrated** local profile (Gate 1) — or the user has been told
  compression is off until they run calibration.
- Passthrough has been confirmed (Gate 2) — or flagged as unverified.
- The user knows to use `pxcore_*` tools for large read-only reference work, not for edits.
