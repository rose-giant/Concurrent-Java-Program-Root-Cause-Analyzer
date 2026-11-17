#!/usr/bin/env python3
"""
score_structured.py - compare structured root-cause JSONL (LLM) against structured ground truth.

Score a prediction file (.json array or .jsonl; ids assigned by position if records have no case_id):
    python score_structured.py --gt gt_structured_prompt_names.jsonl --pred restructured_results.json \\
           --ids_from all_prompts_v2.json --out results.csv

Sanity-check the metric itself (no LLM output needed):
    python score_structured.py --gt gt_structured.jsonl --selftest

Both files use the same schema (case_id, family, bug_class, shared_objects, accesses,
missing_guarantee, conflict, fix_type, fix_action, fix_where, ...). "reasoning" is NOT scored.
Pure standard library.
"""
import argparse, copy, csv, json, random, re, statistics
from collections import defaultdict

ROOT_W = {"family": 0.05, "bug_class": 0.15, "missing_guarantee": 0.15, "conflict_type": 0.10,
          "shared_objects": 0.15, "accesses": 0.20, "conflict": 0.20}
FIX_W = {"fix_type": 0.25, "fix_action": 0.40, "fix_where": 0.35}


# ------------------------------------------------------------ normalisation / set metrics
def nm(x):
    """identifier -> comparable token: last dotted/$ component, lowercase, alphanumerics only."""
    x = str(x or "")
    x = re.split(r"[.$]", x.replace("()", ""))[-1]
    return re.sub(r"[^a-z0-9]", "", x.lower())


def f1(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    tp = len(a & b)
    return 0.0 if tp == 0 else 2 * tp / (len(a) + len(b))


def acc_triples(rec):
    return {(nm(a.get("method")), a.get("op"), nm(a.get("target"))) for a in rec.get("accesses") or []}


def acc_pairs(rec):
    return {(nm(a.get("method")), a.get("op")) for a in rec.get("accesses") or []}


# ------------------------------------------------------------ per-case scoring
def conflict_score(g, p):
    gc, pc = g.get("conflict") or {}, p.get("conflict") or {}
    parts = []
    if gc.get("edges"):
        parts.append(f1({(nm(a), nm(b)) for a, b in gc["edges"]},
                        {(nm(e[0]), nm(e[1])) for e in pc.get("edges") or [] if len(e) == 2}))
    if gc.get("field"):
        parts.append(1.0 if nm(gc["field"]) == nm(pc.get("field")) else 0.0)
    if gc.get("methods"):
        parts.append(f1({nm(m) for m in gc["methods"]}, {nm(m) for m in pc.get("methods") or []}))
    if not parts:  # GT says "no conflict": prediction must also claim none
        empty = not (pc.get("edges") or pc.get("field") or pc.get("methods"))
        return 1.0 if empty else 0.0
    return sum(parts) / len(parts)


def accepted(g, key):
    return {g.get(key)} | {a.get(key) for a in g.get("acceptable_alternatives") or []}


def score_case(g, p):
    r = {
        "family": float(g["family"] == p.get("family")),
        "bug_class": float(g["bug_class"] == p.get("bug_class")),
        "missing_guarantee": float(g["missing_guarantee"] == p.get("missing_guarantee")),
        "conflict_type": float((g.get("conflict") or {}).get("type") == (p.get("conflict") or {}).get("type")),
        "shared_objects": f1({nm(x) for x in g.get("shared_objects") or []},
                             {nm(x) for x in p.get("shared_objects") or []}),
        "accesses_strict": f1(acc_triples(g), acc_triples(p)),
        "accesses_loose": f1(acc_pairs(g), acc_pairs(p)),
        "conflict": conflict_score(g, p),
        "fix_type": float(p.get("fix_type") in accepted(g, "fix_type")),
        "fix_action": float(p.get("fix_action") in accepted(g, "fix_action")),
        "fix_exact": float(p.get("fix_type") == g.get("fix_type") and p.get("fix_action") == g.get("fix_action")),
        "fix_where": f1({nm(x) for x in g.get("fix_where") or []}, {nm(x) for x in p.get("fix_where") or []}),
    }
    r["accesses"] = 0.5 * (r["accesses_strict"] + r["accesses_loose"])
    r["root_cause_score"] = sum(w * r[k] for k, w in ROOT_W.items())
    r["fix_score"] = sum(w * r[k] for k, w in FIX_W.items())
    return r


def operator_of(cid):
    return re.sub(r"-\d+$", "", re.sub(r"^\d+-", "", cid))


def load(path, ids=None):
    """Read a JSON array (.json) or JSON-lines (.jsonl) file -> {case_id: record}.
    Records without a case_id get one by position from `ids` (e.g. the order of all_prompts_v2.json)."""
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):
        data = json.loads(text)
    else:
        data = [json.loads(l) for l in text.splitlines() if l.strip()]
    if ids is not None and any("case_id" not in d for d in data):
        if len(ids) != len(data):
            raise SystemExit(f"{path}: {len(data)} records but {len(ids)} ids - cannot assign ids by position")
        for d, cid in zip(data, ids):
            d.setdefault("case_id", cid)
    out = {}
    for d in data:
        if "case_id" not in d:
            raise SystemExit(f"{path}: record without case_id; pass --ids_from all_prompts_v2.json")
        out[d["case_id"]] = d
    return out


def load_ids(path):
    """ids in file order, from all_prompts*.json ([{"id": ...}, ...]) or a text file with one id per line."""
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):
        return [x["id"] for x in json.loads(text)]
    return [l.strip() for l in text.splitlines() if l.strip()]


# ------------------------------------------------------------ self-test (metric sanity)
def perturbations(gt):
    ids = sorted(gt)
    rng = random.Random(0)

    def rename(g):
        p = copy.deepcopy(g)
        names = {}
        def new(x):
            names.setdefault(x, f"monitor{len(names)}")
            return names[x]
        p["shared_objects"] = [new(x) for x in g["shared_objects"]]
        for a in p["accesses"]:
            a["target"] = new(a["target"])
        p["conflict"]["edges"] = [[new(a), new(b)] for a, b in g["conflict"]["edges"]]
        if g["conflict"]["field"]:
            p["conflict"]["field"] = new(g["conflict"]["field"])
        return p

    def drop_locks(g):
        p = copy.deepcopy(g)
        p["accesses"] = [a for a in p["accesses"] if a["op"] != "lock"]
        p["shared_objects"] = [x for x in p["shared_objects"]
                               if nm(x) not in {nm(a["target"]) for a in g["accesses"] if a["op"] == "lock"}]
        return p

    def alt_fix(g):
        p = copy.deepcopy(g)
        a = g["acceptable_alternatives"][0]
        p["fix_type"], p["fix_action"] = a["fix_type"], a["fix_action"]
        return p

    def wrong_fix(g):
        p = copy.deepcopy(g)
        p["fix_type"], p["fix_action"], p["fix_where"] = "other", "other", []
        return p

    def misread_benign(g):
        p = copy.deepcopy(g)
        p.update(family="non_deadlock", bug_class="order_violation", missing_guarantee="join_ordering")
        p["conflict"] = {"type": "order_violation", "edges": [], "field": None,
                         "methods": [g["accesses"][0]["method"]]}
        p["shared_objects"] = [g["accesses"][0]["target"]]
        return p

    def wrong_class(g):
        pool = [i for i in ids if gt[i]["bug_class"] != g["bug_class"]]
        return copy.deepcopy(gt[rng.choice(pool)])

    return [
        ("perfect copy of GT", lambda g: True, lambda g: copy.deepcopy(g)),
        ("right answer, wrong lock/field names", lambda g: g["bug_class"] != "no_defect", rename),
        ("lock operations not listed", lambda g: any(a["op"] == "lock" for a in g["accesses"]), drop_locks),
        ("different but accepted fix", lambda g: bool(g["acceptable_alternatives"]), alt_fix),
        ("fix missing/wrong", lambda g: True, wrong_fix),
        ("benign case misread as order violation", lambda g: g["bug_class"] == "no_defect", misread_benign),
        ("completely wrong case (floor)", lambda g: True, wrong_class),
    ]


def selftest(gt):
    print(f"{'perturbation':42s} {'n':>3s} {'root':>6s} {'fix':>6s}  accesses  shared  conflict  bug_class")
    for name, applies, fn in perturbations(gt):
        rs = [score_case(g, fn(g)) for g in gt.values() if applies(g)]
        m = lambda k: statistics.mean(r[k] for r in rs)
        print(f"{name:42s} {len(rs):3d} {m('root_cause_score'):6.2f} {m('fix_score'):6.2f}  "
              f"{m('accesses'):8.2f}  {m('shared_objects'):6.2f}  {m('conflict'):8.2f}  {m('bug_class'):9.2f}")


# ------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred")
    ap.add_argument("--ids_from", help="all_prompts_v2.json (or text file): case ids, in the order of the predictions")
    ap.add_argument("--out", default="results.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    gt = load(a.gt)
    if a.selftest:
        return selftest(gt)
    if not a.pred:
        ap.error("--pred is required unless --selftest")
    pred = load(a.pred, load_ids(a.ids_from) if a.ids_from else None)
    cases = sorted(set(gt) & set(pred))
    print(f"GT: {len(gt)} | predictions: {len(pred)} | matched: {len(cases)}")
    miss = sorted(set(gt) - set(pred))
    if miss:
        print("missing predictions (scored as 0 in the means):", miss[:8], "..." if len(miss) > 8 else "")
    res = {c: score_case(gt[c], pred[c]) for c in cases}
    for c in miss:
        res[c] = {k: 0.0 for k in score_case(gt[c], gt[c])}
    cols = (["family", "bug_class", "missing_guarantee", "conflict_type", "shared_objects", "accesses",
             "accesses_strict", "accesses_loose", "conflict", "fix_type", "fix_action", "fix_exact",
             "fix_where", "root_cause_score", "fix_score"])
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "operator", "bug_class_gt"] + cols)
        for c in sorted(res):
            w.writerow([c, operator_of(c), gt[c]["bug_class"]] + [round(res[c][k], 4) for k in cols])
    print(f"\n=== mean over {len(res)} cases ===")
    for k in cols:
        print(f"{k:20s} {statistics.mean(r[k] for r in res.values()):.3f}")
    by = defaultdict(list)
    for c, r in res.items():
        by[operator_of(c)].append(r["root_cause_score"])
    print("\n=== root_cause_score by mutation operator ===")
    for op, v in sorted(by.items()):
        print(f"{op:32s} n={len(v):2d}  mean={statistics.mean(v):.3f}")
    print(f"\nPer-case results written to {a.out}")


if __name__ == "__main__":
    main()