# OpexIA Dev-Log — a relational graph of how this product was built

This directory is a **local, committed knowledge graph of the development history**
of this codebase. Every git commit is a node on a temporal backbone; tasks,
decisions, and bugs are nodes too; typed edges connect them. When something
breaks, an agent (or you) loads the graph, finds a seed node, and **traverses the
relations** to reconstruct what happened, in which commit, at what time, why, and
what it affected.

It is written and maintained automatically by the OpexIA Claude Code plugin
(`/opexia:log`). Nothing here leaves your machine — it is plain files, committed
to your repo, so the full record travels start → production with the code.

## Layout

```
.opexia/devlog/
  entries/<date>-<sha7>-<slug>.md   # one node per commit/task/decision/bug (SOURCE OF TRUTH)
  graph.jsonl                        # derived nodes+edges index — what an agent loads to traverse
  rebuild_graph.py                   # regenerates graph.jsonl from entries/
  README.md                          # this file
```

Entries are the source of truth (edit these). `graph.jsonl` is **derived** — run
`python .opexia/devlog/rebuild_graph.py` to regenerate it after editing entries.

## Node types

| type | meaning |
|------|---------|
| `commit` | one git commit — the temporal backbone (sha, time, message, files). Auto-created by the post-commit hook. |
| `task` | a feature/goal/unit of work, usually spanning several commits |
| `decision` | a design/architecture choice, with its rationale and the alternatives rejected |
| `bug` | a problem encountered and its fix |
| `component` | a module/area of the codebase (e.g. `auth`, `payments`) |

Node ids are prefixed by type: `cmt_<sha7>`, `task_<slug>`, `dec_<slug>`,
`bug_<slug>`, `comp_<name>`.

## Edge types (typed relations)

| edge | from → to | reading |
|------|-----------|---------|
| `follows` | commit → commit | temporal predecessor |
| `implements` | commit → task | this commit advanced that task |
| `touches` | commit → component | this commit changed that area |
| `driven_by` | commit → decision | this commit embodies that decision |
| `fixes` | commit → bug | this commit fixed that bug |
| `introduces` | commit → bug | this commit introduced that bug (regression) |
| `caused_by` | bug → commit | **the debug arrow** — what broke it |
| `supersedes` | decision → decision | replaced an earlier decision |
| `depends_on` | task→task / component→component | dependency |
| `relates_to` | any → any | generic association |

A typical debug traversal:
`bug → caused_by → commit → touches → component → driven_by → decision (→ supersedes → newer decision)`

## Entry frontmatter

```yaml
---
id: cmt_a1b2c3d
type: commit
sha: a1b2c3d4...          # full sha (commit nodes)
timestamp: 2026-08-02T13:45:00+05:30
author: 'Jane Dev'
message: 'add refresh-token rotation'
tags: [auth, security]
enriched: true            # false = stub awaiting Claude's reasoning
files:
  - 'src/auth/refresh.ts'
relations:
  - follows: cmt_9f8e7d6
  - implements: task_token_rotation
  - touches: comp_auth
  - driven_by: dec_rotate_on_use
---
## What        # what changed
## Why / Logic # the approach + reasoning (why THIS way)
## Decisions   # choices made + alternatives rejected
## Agent       # which agent/model did it; subagents involved
```

`enriched: false` marks a commit stub that the post-commit hook wrote but whose
reasoning Claude has not filled in yet. The plugin's Stop hook nudges Claude to
enrich these; you can also run `/opexia:log` to do it on demand.

## Querying

Ask Claude: `/opexia:log query "what happened in auth and why did refresh break?"`
It loads `graph.jsonl`, seeds on the relevant nodes (by tag/component/sha/time),
walks the typed edges, reads the matched entries, and answers with the causal
chain — commit, timestamp, logic, and the decisions behind it.
