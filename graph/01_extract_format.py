#!/usr/bin/env python3
"""
Step 1 - extract the Java programs and reformat them to one statement per line.

Why: your programs are minified onto a single line, so every JPF line number is 1.
After formatting, trace line numbers point at real statements.

Usage examples
  python3 01_extract_format.py --results codes_jpf_results.json \
      --code-json mutants.json --code-json codes.json --work work
  python3 01_extract_format.py --code-json mutants.json --ids 1-rm_sync_block-0 --work work

Selection (default): every case in --results whose classification is a real JPF failure
(Race Condition, Deadlock, Starvation, Uncaught Exception, Termination Error).
  --include-pass   also take Pass cases (useful to compare a mutant with its original)
  --ids A B C      only these ids (overrides the default selection)

Formatter: built-in (no dependencies). Or pass --gjf path/to/google-java-format.jar.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ID_KEYS = ("prompt_id", "id", "case_id", "name")
CODE_KEYS = ("code", "new_code", "source", "java", "program", "mutated_code")
FAIL_CLASSES = {"Race Condition", "Deadlock", "Starvation", "Uncaught Exception", "Termination Error"}


def load_codes(paths, id_key, code_key):
    codes = {}
    for p in paths:
        data = json.load(open(p, encoding="utf-8"))
        if isinstance(data, dict):
            if data and all(isinstance(v, str) for v in data.values()):
                codes.update({str(k): v for k, v in data.items()})
                continue
            lists = [v for v in data.values() if isinstance(v, list)]
            if not lists:
                sys.exit(f"{p}: unsupported JSON layout (dict without a list of records)")
            data = lists[0]
        for rec in data:
            ik = id_key or next((k for k in ID_KEYS if k in rec), None)
            ck = code_key or next((k for k in CODE_KEYS if k in rec), None)
            if ik is None or ck is None:
                sys.exit(f"{p}: cannot find id/code keys; record keys are {list(rec)}. "
                         f"Use --id-key / --code-key.")
            codes[str(rec[ik])] = rec[ck]
    return codes


def main_class(src):
    pub = re.search(r"\bpublic\s+(?:final\s+|abstract\s+)*class\s+(\w+)", src)
    if pub:
        return pub.group(1)
    pos = src.find("static void main")
    decls = [(m.start(), m.group(1)) for m in re.finditer(r"\bclass\s+(\w+)", src)]
    before = [n for s, n in decls if pos >= 0 and s < pos]
    if before:
        return before[-1]
    return decls[0][1] if decls else None


def simple_format(src):
    """Dependency-free formatter: newline after ';' (outside parentheses), '{' and '}'.
    Respects string/char literals and comments; keeps lambda bodies inside call parentheses."""
    out, line = [], []
    indent, paren, stack = 0, 0, []
    i, n = 0, len(src)

    def flush():
        s = "".join(line).strip()
        if s:
            out.append("    " * max(indent, 0) + s)
        line.clear()

    while i < n:
        c, two = src[i], src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            line.append(src[i:j])
            flush()
            i = j + 1
            continue
        if two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line.append(src[i:j])
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            line.append(src[i:j + 1])
            i = j + 1
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        if c == "{":
            line.append(c)
            flush()
            indent += 1
            stack.append(paren)
            paren = 0
            i += 1
            continue
        if c == "}":
            flush()
            indent -= 1
            paren = stack.pop() if stack else 0
            line.append(c)
            i += 1
            rest = src[i:]
            if re.match(r"\s*(else|catch|finally)\b", rest) or re.match(r"\s*[;,)]", rest):
                continue
            flush()
            continue
        if c == ";" and paren == 0:
            line.append(c)
            flush()
            i += 1
            continue
        if c in "\n\r\t":
            c = " "
        if c == " " and line and line[-1].endswith(" "):
            i += 1
            continue
        line.append(c)
        i += 1
    flush()
    return "\n".join(out) + "\n"


def gjf_format(path, jar, java, exports):
    cmd = [java]
    if exports:
        for pkg in ("api", "file", "parser", "tree", "util", "code"):
            cmd += ["--add-exports", f"jdk.compiler/com.sun.tools.javac.{pkg}=ALL-UNNAMED"]
    cmd += ["-jar", jar, "--replace", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--code-json", action="append", required=True,
                    help="JSON with the Java code (repeatable): the files you fed to JPF, e.g. mutants.json, codes.json")
    ap.add_argument("--results", help="codes_jpf_results.json (used to select ids and store the classification)")
    ap.add_argument("--work", default="work")
    ap.add_argument("--id-key")
    ap.add_argument("--code-key")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--include-pass", action="store_true")
    ap.add_argument("--gjf", help="optional google-java-format all-deps jar")
    ap.add_argument("--gjf-java", default="java", help="java executable used to run google-java-format")
    ap.add_argument("--gjf-no-exports", action="store_true", help="omit --add-exports flags (JDK 8-11)")
    a = ap.parse_args()

    codes = load_codes(a.code_json, a.id_key, a.code_key)
    results = {}
    if a.results:
        for r in json.load(open(a.results, encoding="utf-8")):
            results[str(r["prompt_id"])] = r

    if a.ids:
        ids = a.ids
    elif results:
        wanted = FAIL_CLASSES | ({"Pass"} if a.include_pass else set())
        ids = [i for i, r in results.items() if r.get("classification") in wanted]
    else:
        ids = list(codes)

    work = Path(a.work)
    done, missing, bad = 0, [], []
    for cid in ids:
        src = codes.get(cid)
        if not src:
            missing.append(cid)
            continue
        src = re.sub(r"^\s*package\s+[\w.]+\s*;", "", src, flags=re.M)
        cls = main_class(src)
        if not cls:
            bad.append(cid)
            continue
        safe = re.sub(r"[^\w.-]", "_", cid)
        d = work / safe
        (d / "src").mkdir(parents=True, exist_ok=True)
        f = d / "src" / f"{cls}.java"
        f.write_text(src if a.gjf else simple_format(src), encoding="utf-8")
        if a.gjf:
            ok, err = gjf_format(f, a.gjf, a.gjf_java, not a.gjf_no_exports)
            if not ok:
                print(f"[warn] google-java-format failed on {cid}, using built-in: {err.strip()[:120]}")
                f.write_text(simple_format(src), encoding="utf-8")
        meta = {"id": cid, "safe_id": safe, "class": cls,
                "classification": results.get(cid, {}).get("classification")}
        (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        done += 1

    print(f"prepared {done} cases in {work}/")
    if missing:
        print(f"[warn] no code found for {len(missing)} ids (first few: {missing[:5]}). "
              f"Pass the JSON file that holds them via another --code-json.")
    if bad:
        print(f"[warn] no class found for: {bad[:5]}")


if __name__ == "__main__":
    main()
