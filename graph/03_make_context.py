#!/usr/bin/env python3
"""
Step 3 - turn JPF's raw counterexample into a compact evidence document per case.

For every work/<id>/ that has jpf_out/trace.json it writes work/<id>/context.md containing
  - the JPF violation message (shortened)
  - the formatted source with line numbers
  - the interleaving: only concurrency-relevant events (shared-field reads/writes, lock
    enter/exit, wait/notify/join/start/sleep, java.util.concurrent calls), per thread, with
    source line and the locks held
  - thread schedule (who ran how long, number of context switches)
  - per-field lockset table with a race hint (Eraser-style, computed from THIS trace)
  - lock-order edges per thread with a cycle check (deadlock hint)
  - state-graph size

Also writes work/INDEX_context.csv.

Usage
  python3 03_make_context.py --work work [--max-events 120]

The hints are heuristics computed from one trace, not ground truth. Locks are named by the
source expression of `synchronized (expr)`; synchronized methods show up as "method-sync".
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

FIELD_OPS = {"getfield": "READ", "getstatic": "READ", "putfield": "WRITE", "putstatic": "WRITE"}
SYSTEM_PREFIX = ("java.", "javax.", "sun.", "jdk.", "com.sun.", "gov.nasa.")
INVOKE_RE = re.compile(
    r"\.(wait|notify|notifyAll|join|start|sleep|interrupt)\("
    r"|java\.util\.concurrent\.[\w.$]*\.(acquire|release|tryAcquire|lock|unlock|tryLock|await|signal|"
    r"signalAll|countDown|take|put|offer|poll|compareAndSet|incrementAndGet|getAndIncrement|"
    r"decrementAndGet|addAndGet|submit|execute)\(")
SYNC_STMT_RE = re.compile(r"synchronized\s*\(([^)]*)\)")


def shorten(text, width=220, max_lines=12):
    lines = [(l if len(l) <= width else l[:width] + " ...") for l in text.splitlines() if l.strip()]
    return "\n".join(lines[:max_lines])


def lock_expr(src_lines, line):
    for ln in (line, line - 1, line + 1):
        if 1 <= ln <= len(src_lines):
            m = SYNC_STMT_RE.search(src_lines[ln - 1])
            if m:
                return m.group(1).strip()
    return f"<lock@L{line}>"


def build_events(steps, src_lines):
    events, held = [], defaultdict(list)
    order_edges = defaultdict(set)   # thread -> {(outer, inner)}
    started = False
    for s in steps:
        th, op, insn, line = s["th"], s["op"], s["insn"], s["line"]
        src = src_lines[line - 1].strip() if 1 <= line <= len(src_lines) else ""
        kind = target = None
        if op in FIELD_OPS:
            owner = insn.split(None, 1)[1] if " " in insn else insn
            if owner.startswith(SYSTEM_PREFIX):
                continue
            kind, target = FIELD_OPS[op], owner
        elif op == "monitorenter":
            kind, target = "LOCK", lock_expr(src_lines, line)
            for outer in held[th]:
                if outer != target:
                    order_edges[th].add((outer, target))
            held[th].append(target)
        elif op == "monitorexit":
            kind = "UNLOCK"
            target = held[th].pop() if held[th] else "?"
        elif op.startswith("invoke") and INVOKE_RE.search(insn):
            kind, target = "CALL", insn.split(None, 1)[1] if " " in insn else insn
            if re.search(r"\.start\(", insn):
                started = True
        else:
            continue
        locks = list(held[th]) + (["method-sync"] if s.get("sync") else [])
        events.append({"th": th, "line": line, "kind": kind, "target": target,
                       "locks": locks, "src": src, "m": f"{s['cls']}.{s['m']}",
                       "after_start": started})
    return events, order_edges


def collapse(events):
    out = []
    for e in events:
        if out and all(out[-1][k] == e[k] for k in ("th", "line", "kind", "target", "locks")):
            out[-1]["count"] += 1
        else:
            out.append(dict(e, count=1))
    return out


def find_cycle(order_edges):
    graph = defaultdict(set)
    for th, es in order_edges.items():
        for a, b in es:
            graph[a].add(b)
    color, stack = {}, []

    def dfs(u):
        color[u] = 1
        stack.append(u)
        for v in graph[u]:
            if color.get(v, 0) == 1:
                return stack[stack.index(v):] + [v]
            if color.get(v, 0) == 0:
                c = dfs(v)
                if c:
                    return c
        color[u] = 2
        stack.pop()
        return None

    for n in list(graph):
        if color.get(n, 0) == 0:
            c = dfs(n)
            if c:
                return c
    return None


def build_context(case, max_events):
    meta = json.loads((case / "meta.json").read_text(encoding="utf-8"))
    src_file = next((case / "src").glob("*.java"))
    src_lines = src_file.read_text(encoding="utf-8").splitlines()
    trace_p = case / "jpf_out" / "trace.json"
    graph_p = case / "jpf_out" / "graph.json"
    trace = json.loads(trace_p.read_text(encoding="utf-8")) if trace_p.exists() else None
    graph = json.loads(graph_p.read_text(encoding="utf-8")) if graph_p.exists() else None

    md = [f"# JPF evidence for case `{meta['id']}`", ""]
    if trace is None:
        md.append("JPF reported no counterexample path for this case (no property violation, "
                  "timeout, or the violation produced no replayable path).")
    else:
        md += ["## JPF violation (shortened)", "```", shorten(trace["error"]), "```", ""]

    md += ["## Source (formatted; line numbers match the trace)", "```java"]
    md += [f"{i:3d}  {l}" for i, l in enumerate(src_lines[:200], 1)]
    md += ["```", ""]

    info = {"id": meta["id"], "classification": meta.get("classification"), "events": 0,
            "switches": 0, "race_hint": "", "cycle": ""}

    if trace is not None:
        events, order_edges = build_events(trace["steps"], src_lines)
        rows = collapse(events)
        info["events"] = len(events)

        # thread schedule
        runs = []
        for e in events:
            if runs and runs[-1][0] == e["th"]:
                runs[-1][1] += 1
            else:
                runs.append([e["th"], 1])
        info["switches"] = max(len(runs) - 1, 0)
        md += ["## Schedule (thread: number of concurrency-relevant events)", "",
               " -> ".join(f"{t}({n})" for t, n in runs[:60]) + (" -> ..." if len(runs) > 60 else ""),
               f"", f"context switches between relevant events: {info['switches']}", ""]

        # interleaving table
        if len(rows) > max_events:
            keep = rows[:20] + [None] + rows[-(max_events - 20):]
        else:
            keep = rows
        md += ["## Interleaving to the violation", "",
               "| # | thread | line | event | target | locks held | source |",
               "|---|--------|------|-------|--------|------------|--------|"]
        for i, r in enumerate(keep, 1):
            if r is None:
                md.append("| ... | | | | | | (middle of trace omitted) |")
                continue
            ev = r["kind"] + (f" x{r['count']}" if r["count"] > 1 else "")
            lk = ", ".join(r["locks"]) or "-"
            src = r["src"].replace("|", "\\|")[:90]
            md.append(f"| {i} | {r['th']} | {r['line']} | {ev} | {r['target'].replace('|', '/')} | {lk} | `{src}` |")
        md.append("")

        # lockset table (Eraser-style, ignore accesses before the first Thread.start)
        acc = defaultdict(list)
        for e in events:
            if e["kind"] in ("READ", "WRITE") and e["after_start"]:
                acc[e["target"]].append(e)
        md += ["## Shared-field accesses and locksets (heuristic, from this trace)", "",
               "| field | threads | reads | writes | lines | common lock |",
               "|-------|---------|-------|--------|-------|-------------|"]
        hints = []
        for fld, es in sorted(acc.items()):
            ths = sorted({e["th"] for e in es})
            reads = sum(e["kind"] == "READ" for e in es)
            writes = sum(e["kind"] == "WRITE" for e in es)
            common = set(es[0]["locks"])
            for e in es[1:]:
                common &= set(e["locks"])
            lines = sorted({e["line"] for e in es})
            md.append(f"| {fld} | {', '.join(ths)} | {reads} | {writes} | {lines} | "
                      f"{', '.join(sorted(common)) or 'NONE'} |")
            if len(ths) >= 2 and writes and not common:
                hints.append(fld)
        md.append("")
        if hints:
            info["race_hint"] = ";".join(hints)
            md.append("Race hint: " + ", ".join(hints) +
                      " is accessed by >=2 threads, written at least once, and no single lock "
                      "protects all accesses.")
            md.append("")

        # lock order
        if order_edges:
            md += ["## Lock acquisition order (outer -> inner)", ""]
            for th, es in sorted(order_edges.items()):
                md.append(f"- {th}: " + "; ".join(f"{a} -> {b}" for a, b in sorted(es)))
            cyc = find_cycle(order_edges)
            if cyc:
                info["cycle"] = " -> ".join(cyc)
                md += ["", "Lock-order cycle: " + " -> ".join(cyc) + "  (possible deadlock)"]
            md.append("")

    if graph:
        nodes = {e[0] for e in graph["edges"]} | {e[1] for e in graph["edges"]}
        md += ["## State graph", "",
               f"states seen: {len(nodes)}, transitions: {len(graph['edges'])}, "
               f"end states: {len(graph['end_states'])}, truncated: {graph['truncated']}", ""]

    (case / "context.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="work")
    ap.add_argument("--max-events", type=int, default=120)
    a = ap.parse_args()

    infos = []
    for case in sorted(Path(a.work).iterdir()):
        if (case / "meta.json").exists() and (case / "jpf_out").exists():
            infos.append(build_context(case, a.max_events))
    with open(Path(a.work) / "INDEX_context.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "classification", "events", "switches", "race_hint", "cycle"])
        w.writeheader()
        w.writerows(infos)
    print(f"wrote context.md for {len(infos)} cases -> {Path(a.work) / 'INDEX_context.csv'}")


if __name__ == "__main__":
    main()
