# OpexIA Plugin for Claude Code — Developer Guide

A step-by-step guide to installing and using the **OpexIA plugin** inside Claude
Code. Written for developers on any machine — you do not need to know anything
about how OpexIA works internally. Follow the steps, run the commands, done.

---

## 1. What this plugin gives you

Once installed, the plugin adds a set of **slash commands** and **tools** to your
Claude Code session. You keep working the way you normally do — the plugin adds
four capabilities on top:

| Capability | Command | What it does for you |
|---|---|---|
| **Instrument for observability** | `/opexia:instrument` | Wires your project to send traces to OpexIA so you can see what your app/agent is doing in the dashboard. |
| **Token compression** | `/opexia:compress` | Cuts the number of input tokens Claude Code spends reading bulky output — lower cost, more room in context. |
| **Ship Check (PR gate)** | `opexia shipcheck` | Catches expensive or unsafe prompt/model changes *before* they merge. No AI call, runs in CI. |
| **Agent map & security audit** | `opexia audit` | Draws a map of your agents/tools/servers and flags security issues. Runs entirely on your machine — nothing leaves it. |

You do **not** need all four. Most teams start with `/opexia:instrument` and add
the rest when they need them.

---

## 2. Before you start (requirements)

You need:

- **Claude Code** installed and working (you can open it and run `/help`).
- **Python 3.9+** available on your PATH (`python --version`).
- Your **OpexIA project credentials** — your team lead / OpexIA admin gives you
  these five values:
  - `OPEXIA_ORG_ID`
  - `OPEXIA_WORKSPACE_ID`
  - `OPEXIA_PROJECT_ID`
  - `OPEXIA_API_KEY`
  - `OPEXIA_INGEST_URL`

> You do **not** need these five values just to *install* the plugin — only when
> you run `/opexia:instrument` and want traces to actually reach the dashboard.

---

## 3. Install the plugin

Two commands, run inside Claude Code. The first registers the plugin's
marketplace from GitHub; the second installs it.

```
/plugin marketplace add star-56/opexia-cli-plugin
/plugin install opexia@opexia
```

That's the whole install. (`star-56/opexia-cli-plugin` is the GitHub repo —
`https://github.com/star-56/opexia-cli-plugin`. Claude Code fetches the plugin
from there directly; you don't need to clone anything.)

### Confirm it installed

```
/plugin
```

You should see **opexia** in the list of installed plugins. That's it — the new
commands (`/opexia:instrument`, `/opexia:compress`) and tools are now available.

> **Restart tip:** if the new commands don't show up right away, fully close and
> reopen Claude Code so it reloads plugins.

---

## 4. Use it

### 4a. Instrument your project — `/opexia:instrument`

Open Claude Code **inside your project directory**, then run:

```
/opexia:instrument
```

The plugin inspects your project, figures out the right way to connect it to
OpexIA, and does the wiring for you. It then **verifies** that a real trace
reaches OpexIA before it reports success — so you're never left guessing whether
it worked.

When it's done:

1. It writes placeholder credential names into an `.env.example` file (it never
   writes real secrets for you).
2. Copy those into your own `.env` and fill in the five values from Section 2.
3. Re-run the verify step when the plugin asks, and confirm the trace shows up in
   your OpexIA dashboard.

**Useful variations** (just type them as the command):

```
/opexia:instrument use direct http
/opexia:instrument attribute per end user
```

If you're not sure which to use, run plain `/opexia:instrument` and let the plugin
recommend.

> **Frontend safety:** for browser or mobile apps, the plugin deliberately
> **refuses** to put your API key in client code and routes through your server
> instead. This is intentional — it protects your key.

---

### 4b. Save tokens — `/opexia:compress`

```
/opexia:compress
```

This sets up **token compression** for your Claude Code session. In plain terms:
when a tool returns a big, dense chunk of output (a long file, command output,
logs), the plugin can hand it to the model as an **image the model reads with its
own vision** instead of as raw text — which costs far fewer input tokens. Anything
the model must reproduce exactly (ids, file paths, hashes, code you're editing)
always stays as text.

Two things to know:

1. **It's safe-by-default.** Until it's set up and confirmed for your model, it
   simply returns normal text — it never silently degrades anything.
2. **It asks for a one-time setup** so it can confirm compression genuinely works
   for the model you're using. Follow the prompts the command gives you.

For **larger savings** across your whole session (not just tool output), the
command can point you at an optional companion CLI:

```
/opexia:compress proxy
```

---

### 4c. Guard your PRs — `opexia shipcheck`

`shipcheck` is a command-line check you run in your terminal or CI. It reviews a
prompt / model / config change **before it merges** and tells you the cost and
safety impact — **without making any AI call**.

```
pip install "opexia-trace[shipcheck]"
opexia shipcheck
```

Exit codes:
- `0` — the change is fine.
- `1` — the policy failed (e.g. a change that would quietly increase cost).
- `2` — the check couldn't run.

Drop it into your CI pipeline as a required step to keep prompt regressions from
shipping.

---

### 4d. Map & audit your agents — `opexia audit`

If your project uses agents, tools, MCP servers, or hooks, this draws a map of the
whole system and flags security problems.

```
pip install opexia-trace
opexia audit --map agentmap.html
```

It produces a **self-contained, offline HTML map** you can open in any browser. It
runs **100% on your machine** — no network call, nothing it finds ever leaves your
computer.

---

## 5. Quick reference

```
# Install
/plugin marketplace add star-56/opexia-cli-plugin
/plugin install opexia@opexia
/plugin                         # confirm it's installed

# Use (inside your project)
/opexia:instrument              # connect project to OpexIA
/opexia:compress                # turn on token savings
/opexia:compress proxy          # bigger savings (optional companion CLI)

# Command-line companions
pip install "opexia-trace[shipcheck]"
opexia shipcheck                # PR gate: cost/safety of prompt changes
opexia audit --map agentmap.html   # local agent map + security audit
```

---

## 6. Troubleshooting

| Symptom | Do this |
|---|---|
| Commands (`/opexia:...`) don't appear | Run `/plugin` to confirm it installed; fully restart Claude Code so plugins reload. |
| Instrument finished but no traces in the dashboard | Make sure your `.env` has all five `OPEXIA_*` values filled in (not the placeholders), then re-run the verify step. |
| "Python not found" | Install Python 3.9+ and make sure `python --version` works in your terminal. |
| `opexia shipcheck` / `opexia audit` "command not found" | Run `pip install opexia-trace` (add `[shipcheck]` for the PR gate). |
| Compression doesn't seem to save anything | It only compresses after the one-time setup in `/opexia:compress` confirms it works for your model — until then it safely stays as text. |
| Still stuck | Contact your OpexIA support contact with the exact command you ran and the message you saw. |

---

## 7. Good to know

- **Your data stays put.** The compression and audit features run locally —
  nothing they process is sent anywhere. Instrumentation sends traces only to the
  OpexIA endpoint *you* configure.
- **Secrets are never written for you.** The plugin only writes placeholder names
  into `.env.example`; you fill in the real values in your own `.env`, which should
  stay out of version control.
- **Licensing.** The plugin is free to install and use to instrument your own
  applications. You may not redistribute, resell, or fork it.

---

*Questions your team can't answer? Reach out to your OpexIA contact — include the
command you ran and the exact output you saw.*
