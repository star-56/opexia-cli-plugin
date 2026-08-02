---
id: TYPE_slug            # cmt_<sha7> | task_<slug> | dec_<slug> | bug_<slug> | comp_<name>
type: commit             # commit | task | decision | bug | component
sha:                     # full sha — commit nodes only
timestamp: 2026-01-01T00:00:00+00:00
author: ''
message: ''              # short title of this node
tags: []
enriched: true
files: []                # paths this node concerns (commit/task)
relations:
  - follows: cmt_xxxxxxx        # edge: TYPE: target-id  (see README for edge types)
---

## What
<what this node is / what changed>

## Why / Logic
<the approach and the reasoning — why it was done this way, not just what>

## Decisions
<design choices made here, and the alternatives considered and rejected>

## Agent
<which agent/model produced this work; any subagents involved>
