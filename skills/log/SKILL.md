---
name: log
description: Maintain and query a local, relational, agent-queryable dev-log — a committed knowledge graph of how this codebase was built. Use when the user wants to set up the OpexIA dev-log, record what was implemented at a checkpoint, enrich commit entries with the reasoning/logic behind them, or QUERY the build history to debug ("what happened in auth and why did it break", "which commit introduced this, what decision drove it"). Every git commit is a node; tasks, decisions, and bugs are nodes; typed edges connect them so the history is traversable. Local, zero-egress, never blocks a commit.
when_to_use: "Setting up or querying the OpexIA relational dev-log; recording/enriching what an agent implemented at a checkpoint; tracing a bug back through commits, decisions, and components."
user-invocable: true
argument-hint: "[init | query \"<question>\" | rebuild | (default: enrich pending commit entries)]"
---

# OpexIA Dev-Log — a relational build-history graph

You maintain a **local, committed knowledge graph of how THIS product was built**,
and you query it to debug. Every git commit is a node on a temporal backbone;
`task`, `decision`, `bug`, and `component` nodes hang off it via **typed edges**.
A future agent loads the graph, seeds on a node, and **traverses the relations**
to reconstruct what happened, when, in which commit, why, and what it affected.

Free-form user instruction (if any): `$ARGUMENTS`

The graph model (node types, edge types, frontmatter) is specified in
`templates/devlog-README.md` in this skill — that same file is copied into the
user's repo as `.opexia/devlog/README.md`. Read it; it is the schema you follow.

---

## RULE 0 — non-negotiable

1. **Local, zero-egress.** The dev-log is plain files under `.opexia/devlog/`,
   committed to the user's own repo. Nothing is posted, uploaded, or sent to any
   service. It is build history, kept on their machine.
2. **Never block or slow a commit.** The git `post-commit` hook is fail-open by
   design (always exits 0). Never make the log a gate on committing.
3. **The user owns commits.** You write and edit the dev-log files; you do NOT run
   `git commit`/`push`. When the log is ready, tell the user to commit
   `.opexia/devlog/` (so the history travels with the code).
4. **Enrichment is honest.** When you fill in the "why/logic", write what actually
   happened and why — the real approach, the real decisions, the real alternatives
   rejected. A fabricated rationale poisons every future debug traversal. If you
   don't know why a past commit did something, say so in the entry rather than guess.

---

## Route on `$ARGUMENTS`

- **`init`** → set up the dev-log in this repo (below).
- **`query "<question>"`** → traverse the graph to answer (below).
- **`rebuild`** → `python .opexia/devlog/rebuild_graph.py` to regenerate `graph.jsonl` from entries.
- **anything else / empty** → **enrich**: fill in the reasoning for any pending
  (`enriched: false`) commit entries (below). This is also what the Stop hook asks
  you to do automatically.

---

## `init` — set up the dev-log

1. Create `.opexia/devlog/entries/` and an empty `.opexia/devlog/graph.jsonl`.
2. Copy this skill's `templates/devlog-README.md` → `.opexia/devlog/README.md` and
   `templates/rebuild_graph.py` → `.opexia/devlog/rebuild_graph.py`.
3. Install the git hook. If `.git/hooks/post-commit` does **not** exist: copy this
   skill's `templates/post-commit` there and `chmod +x` it. If it **already
   exists**: do NOT clobber it — show the user, and append a line that runs our
   hook body (or chain it), only after they agree.
4. The **Stop hook ships with the plugin** and is already active — it will nudge
   you to enrich new commit entries automatically. Nothing to install for it.
5. Write one genesis `task` node describing the project's current state/goal so the
   graph has a root beyond commits (use `templates/entry-template.md`).
6. Run `rebuild`, then tell the user to `git add .opexia/devlog && git commit`.

Confirm what you created and that future commits will auto-log.

---

## enrich — fill the reasoning + wire the relations

Triggered on demand or by the Stop hook whenever commit stubs carry `enriched: false`.

For **each** `.opexia/devlog/entries/*.md` with `enriched: false`:

1. Read the commit: `git show --stat <sha>` and the diff for the changed files.
2. Using that diff **and** what you did this session (you have the real context),
   fill the body:
   - **What** — what changed, concretely.
   - **Why / Logic** — the approach and the reasoning; why this way, not just what.
   - **Decisions** — choices made + alternatives considered and rejected.
   - **Agent** — which agent/model did the work (you), and any subagents.
3. Add the **semantic edges** to the frontmatter `relations:` list — the ones that
   need understanding (the hook already added `follows`):
   - `implements: task_<slug>` — create/point at the `task` node this advances.
   - `touches: comp_<name>` — the component(s) changed (create `component` nodes as needed).
   - `driven_by: dec_<slug>` — if a design decision governs this; create a `decision` node.
   - `fixes: bug_<slug>` / `introduces: bug_<slug>` — if it fixes or regresses a bug;
     on a `bug` node add `caused_by: cmt_<sha7>` pointing at the culprit commit.
   Create any referenced `task`/`decision`/`bug`/`component` node as its own entry
   file (`templates/entry-template.md`) if it doesn't exist yet.
4. Set `enriched: true`.
5. When all pending entries are done, run `rebuild`. Then remind the user to commit
   the updated `.opexia/devlog/`.

Keep it tight and true. One good paragraph of real reasoning beats a page of filler.

---

## query — traverse the graph to answer

1. Load `.opexia/devlog/graph.jsonl` (one read: node + edge records). If it looks
   stale vs `entries/`, run `rebuild` first.
2. **Seed**: pick the nodes matching the question — by `tags`/component, by `sha`,
   by time window, or by matching entry titles/text.
3. **Traverse** the typed edges from the seeds, following the relations that fit the
   question. For a "what broke / why" question, walk `caused_by` → commit, then
   `touches` → component, then `driven_by` → decision (and `supersedes` to see if a
   later decision changed it). For "history of X", walk `follows` along commits that
   `touch`/`implement` X.
4. **Read** the matched entry files for the real "why/logic".
5. **Answer** with the causal chain, naming commit ids, timestamps, the logic, and
   the decisions — e.g. "introduced in `cmt_a1b2c3d` (2026-08-02 13:45), which
   touched `comp_auth` under decision `dec_rotate_on_use`, later superseded by …".

The value is the *relation*, not a flat list — always return the chain, not just the node.
