#!/usr/bin/env python3
"""Rebuild .opexia/devlog/graph.jsonl from the entry files (the source of truth).

The entries (Markdown + YAML-ish frontmatter) are what humans and Claude edit.
This script materialises them into a single append-free graph index that a
querying agent loads in one read and traverses by typed edges.

Output lines (JSONL), each a self-describing record:
  {"kind":"node","id":..,"type":..,"ts":..,"title":..,"sha":..,"tags":[..],
   "enriched":bool,"entry":"<relative path>"}
  {"kind":"edge","from":..,"type":..,"to":..}

Deterministic + dependency-free (stdlib only). A missing/garbled entry is
skipped with a warning, never fatal — telemetry about your own build must not
break your build.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEVLOG = Path(".opexia/devlog")
ENTRIES = DEVLOG / "entries"
OUT = DEVLOG / "graph.jsonl"


def parse_frontmatter(text: str) -> dict:
    """Parse the leading --- ... --- block. Supports scalars, a `files:` list of
    `- item`, and a `relations:` list of `- type: target`. No external YAML dep."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    body = text[3:end].strip("\n").splitlines()
    fm: dict = {}
    key = None
    for raw in body:
        line = raw.rstrip()
        if not line.strip():
            continue
        indented = line[0] in " \t"
        stripped = line.strip()
        if not indented and ":" in stripped and not stripped.startswith("- "):
            k, _, v = stripped.partition(":")
            key = k.strip()
            v = v.strip()
            if v == "" or v == "[]":
                fm[key] = [] if v == "" else []
                if v == "[]":
                    key = None
            else:
                fm[key] = _scalar(v)
                key = None
        elif indented and stripped.startswith("- "):
            item = stripped[2:].strip()
            if key is None:
                continue
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                if ":" in item:  # relation: "type: target"
                    t, _, tgt = item.partition(":")
                    fm[key].append({t.strip(): _scalar(tgt.strip())})
                else:
                    fm[key].append(_scalar(item))
    return fm


def _scalar(v: str):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1].replace("''", "'")
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def main() -> int:
    if not ENTRIES.is_dir():
        print(f"no entries dir at {ENTRIES}", file=sys.stderr)
        return 1
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set = set()
    for path in sorted(ENTRIES.glob("*.md")):
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        nid = fm.get("id")
        if not nid:
            continue
        nodes[nid] = {
            "kind": "node", "id": nid, "type": fm.get("type", "note"),
            "ts": fm.get("timestamp", ""), "title": fm.get("message", ""),
            "sha": fm.get("sha", ""), "tags": fm.get("tags", []) or [],
            "enriched": bool(fm.get("enriched", False)),
            "entry": str(path.as_posix()),
        }
        for rel in fm.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            for etype, target in rel.items():
                sig = (nid, etype, target)
                if sig in seen_edges:
                    continue
                seen_edges.add(sig)
                edges.append({"kind": "edge", "from": nid, "type": etype, "to": target})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for n in nodes.values():
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"graph.jsonl: {len(nodes)} nodes, {len(edges)} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
