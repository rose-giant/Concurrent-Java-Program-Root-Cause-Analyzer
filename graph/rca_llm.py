#!/usr/bin/env python3
"""
Root-cause-only LLM evaluation on JPF counterexamples.

Step 1  build : codes.json + codes_jpf_results.json  ->  rca_inputs.json
                (one object per failing program: id, prompt, code, counterexample)
Step 2  run   : rca_inputs.json -> LLM -> rca_out/<id>.md  (ground-truth format, sections 1-3)
                + rca_out/_all.json

No third-party packages needed (stdlib only).

Usage
  python rca_llm.py build --codes codes.json --results codes_jpf_results.json --out rca_inputs.json
  export ANTHROPIC_API_KEY=...
  python rca_llm.py run --inputs rca_inputs.json --outdir rca_out --model claude-sonnet-4-6 -j 4

  # any OpenAI-compatible server (vLLM, Ollama, OpenAI, ...):
  export OPENAI_API_KEY=...        # any string for local servers
  python rca_llm.py run --inputs rca_inputs.json --provider openai \
        --base-url http://localhost:8000/v1 --model Qwen/Qwen2.5-Coder-32B-Instruct

  # try 2 cases first:
  python rca_llm.py run --inputs rca_inputs.json --limit 2
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------- prompt ----
# The only text stored in every JSON object (kept tiny on purpose).
TINY_PROMPT = (
    "Find the root cause of the concurrency bug in `code`, using ONLY `counterexample` "
    "(the JPF output) and `code`. Do not run, fix, or speculate beyond what they show. "
    "Fill the template; write n/a where the evidence does not say."
)

# Shared by all cases, sent once as the system message (not repeated in each object).
SYSTEM = """You are an annotator of Java PathFinder (JPF) concurrency bugs.
You get one JSON object with: "prompt", "code" (buggy Java program), "counterexample" (JPF output).
Rules:
- Use only the code and the counterexample. No outside assumptions, no tools, no re-running anything.
- Do not reason beyond the evidence. If something is not shown, write n/a.
- Root cause only. Do NOT propose or write a fix.
- Tick exactly one box per group with [x]. Output ONLY the markdown template below, filled in, nothing before or after.

TEMPLATE (copy the structure exactly; replace <...>):

# Ground Truth: <case id>

## 1. Bug classification (ConFixAgent taxonomy)

**Family**

* [ ] Non-deadlock
* [ ] Deadlock
* [ ] Other / out of scope (e.g. non-termination, unrelated exception, compile error)

**Non-deadlock class** *(only if non-deadlock)*

<e.g. data race, atomicity violation, order violation, starvation, ... or n/a>

**Memory-access pattern**

Selected pattern: **<pattern or none>**

<one or two sentences>

**Deadlock type**

<resource / communication / n/a, one sentence>

---

## 2. JPF evidence

* **Violated property / error message:**

  <property class and message from the counterexample>

* **Location (file:line):**

  <from the counterexample, or n/a>

* **Counterexample summary (threads, key steps):**

  <numbered steps, only what the counterexample shows>

---

## 3. Root cause

**Shared state** *(variable / object / lock):*

<...>

**Accesses involved**

| Thread | Method | Line | Operation (R/W/lock/wait/notify) |
| --- | --- | --- | --- |
| <...> | <...> | <...> | <...> |

**Guarantee that is missing** *(what should be atomic, ordered, or protected):*

<...>

**Buggy interleaving** *(2 to 4 steps)*

1. <...>

**Why this produces the JPF symptom:**

<...>
"""

# ---------------------------------------------------------------- build -----
def has_counterexample(details: str) -> bool:
    # a real JPF property violation prints "error #N: ..." in the results block
    return bool(details) and re.search(r"^error #\d+", details, re.M) is not None

def build(a):
    codes = {c["id"]: c["code"] for c in json.load(open(a.codes))}
    res = json.load(open(a.results))
    out, skipped = [], {"no_counterexample": 0, "no_code": 0, "code_too_big": 0}
    for r in res:
        cid = r["prompt_id"]
        det = r.get("jpf_details") or ""
        if not has_counterexample(det):
            skipped["no_counterexample"] += 1
            continue
        code = codes.get(cid)
        if not code:
            skipped["no_code"] += 1
            continue
        if len(code) > a.max_code_chars:
            skipped["code_too_big"] += 1
            print(f"skip {cid}: code is {len(code)} chars", file=sys.stderr)
            continue
        out.append({"id": cid, "prompt": TINY_PROMPT, "code": code, "counterexample": det})
    json.dump(out, open(a.out, "w"), indent=2, ensure_ascii=False)
    print(f"wrote {len(out)} objects to {a.out}; skipped {skipped}")

# ---------------------------------------------------------------- LLM -------
def post(url, headers, body, retries=5):
    data = json.dumps(body).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 529) and i < retries - 1:
                time.sleep(2 ** (i + 1)); continue
            raise RuntimeError(f"HTTP {e.code}: {msg[:500]}")
        except (urllib.error.URLError, TimeoutError):
            if i < retries - 1:
                time.sleep(2 ** (i + 1)); continue
            raise

def call_llm(a, user_text):
    if a.provider == "anthropic":
        r = post(
            (a.base_url or "https://api.anthropic.com") + "/v1/messages",
            {"content-type": "application/json",
             "x-api-key": os.environ["ANTHROPIC_API_KEY"],
             "anthropic-version": "2023-06-01"},
            {"model": a.model, "max_tokens": a.max_tokens, "temperature": 0,
             "system": SYSTEM, "messages": [{"role": "user", "content": user_text}]})
        return "".join(b.get("text", "") for b in r["content"])
    r = post(
        (a.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
        {"content-type": "application/json",
         "authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "none")},
        {"model": a.model, "max_tokens": a.max_tokens, "temperature": 0,
         "messages": [{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user_text}]})
    return r["choices"][0]["message"]["content"]

def clean(text):
    t = text.strip()
    t = re.sub(r"^```(?:markdown|md)?\s*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip() + "\n"

def run(a):
    items = json.load(open(a.inputs))
    if a.ids:
        items = [x for x in items if x["id"] in set(a.ids)]
    if a.limit:
        items = items[: a.limit]
    os.makedirs(a.outdir, exist_ok=True)

    def work(it):
        path = os.path.join(a.outdir, it["id"] + ".md")
        if os.path.exists(path) and not a.overwrite:
            return it["id"], "exists", open(path).read()
        # the LLM receives the JSON object itself (prompt + code + counterexample)
        text = clean(call_llm(a, json.dumps(it, indent=2, ensure_ascii=False)))
        open(path, "w").write(text)
        return it["id"], "ok", text

    results, fails = {}, 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(work, it): it["id"] for it in items}
        for f in as_completed(futs):
            cid = futs[f]
            try:
                _, status, text = f.result()
                results[cid] = text
                print(f"[{status}] {cid}")
            except Exception as e:
                fails += 1
                print(f"[FAIL] {cid}: {e}", file=sys.stderr)
    json.dump(results, open(os.path.join(a.outdir, "_all.json"), "w"), indent=2, ensure_ascii=False)
    print(f"done: {len(results)} ok, {fails} failed -> {a.outdir}/")

# ---------------------------------------------------------------- cli -------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)

    b = s.add_parser("build", help="make rca_inputs.json")
    b.add_argument("--codes", default="codes.json")
    b.add_argument("--results", default="codes_jpf_results.json")
    b.add_argument("--out", default="rca_inputs.json")
    b.add_argument("--max-code-chars", type=int, default=200_000)
    b.set_defaults(fn=build)

    r = s.add_parser("run", help="send each object to the LLM")
    r.add_argument("--inputs", default="rca_inputs.json")
    r.add_argument("--outdir", default="rca_out")
    r.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    r.add_argument("--model", default="claude-sonnet-4-6")
    r.add_argument("--base-url", default=None)
    r.add_argument("--max-tokens", type=int, default=2500)
    r.add_argument("-j", "--jobs", type=int, default=4)
    r.add_argument("--ids", nargs="*", help="only these case ids")
    r.add_argument("--limit", type=int, help="only the first N cases")
    r.add_argument("--overwrite", action="store_true")
    r.set_defaults(fn=run)

    a = p.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()