#!/usr/bin/env python3
"""
Step 2 - compile every prepared case with Java 8 and run JPF with the TraceDump listener.

Usage
  python3 02_run_jpf.py --work work --jpf-core /path/to/jpf-core --java8-home /path/to/jdk8 -j 4
  python3 02_run_jpf.py --work work --jpf-core ... --ids 1-rm_sync_block-0      # smoke test, one case

Per case it writes (inside work/<id>/):
  classes/           compiled bytecode (javac -g)
  run.jpf            generated config = base.jpf + target/classpath/TraceDump
  jpf.log            full JPF console output
  jpf_out/trace.json counterexample path (only if JPF found a violation)
  jpf_out/graph.json, graph.dot   explored state graph
  status.json        return code, timeout flag, violation flag, seconds
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def set_prop(text, key, value, append=False):
    exists = re.search(r"^\s*" + re.escape(key) + r"\s*\+?=", text, re.M) is not None
    if append and exists:
        return text.rstrip() + f"\n{key}+=,{value}\n"
    return text.rstrip() + f"\n{key}={value}\n"


def exe(java_home, name):
    return str(Path(java_home) / "bin" / name) if java_home else name


def run_case(case_dir, a, base_text):
    meta = json.loads((case_dir / "meta.json").read_text(encoding="utf-8"))
    status = {"id": meta["id"], "class": meta["class"], "compiled": False, "ran": False,
              "returncode": None, "timed_out": False, "violation": False,
              "has_trace": False, "seconds": None}
    classes = case_dir / "classes"
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir()
    out_dir = case_dir / "jpf_out"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    srcs = [str(p) for p in (case_dir / "src").glob("*.java")]
    r = subprocess.run([exe(a.java8_home, "javac"), "-g", "-nowarn", "-d", str(classes)] + srcs,
                       capture_output=True, text=True)
    (case_dir / "compile.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        (case_dir / "status.json").write_text(json.dumps(status, indent=2))
        return status
    status["compiled"] = True

    cfg = base_text
    cfg = set_prop(cfg, "target", meta["class"])
    cfg = set_prop(cfg, "classpath", classes.resolve().as_posix())
    if re.search(r"^\s*listener\s*\+?=", cfg, re.M):
        cfg = set_prop(cfg, "listener", "TraceDump", append=True)
    else:
        cfg = set_prop(cfg, "listener", "TraceDump")
    cfg = set_prop(cfg, "native_classpath", Path(a.listener_jar).resolve().as_posix(), append=True)
    cfg = set_prop(cfg, "tracedump.out", out_dir.resolve().as_posix())
    cfg = set_prop(cfg, "vm.store_steps", "true")
    (case_dir / "run.jpf").write_text(cfg, encoding="utf-8")

    runjpf = Path(a.jpf_core) / "build" / "RunJPF.jar"
    t0 = time.time()
    try:
        r = subprocess.run([exe(a.java8_home, "java"), "-jar", str(runjpf), "run.jpf"],
                           cwd=case_dir, capture_output=True, text=True, timeout=a.timeout)
        log = r.stdout + "\n" + r.stderr
        status["returncode"] = r.returncode
    except subprocess.TimeoutExpired as e:
        status["timed_out"] = True
        log = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
    status["seconds"] = round(time.time() - t0, 1)
    status["ran"] = True
    (case_dir / "jpf.log").write_text(log, encoding="utf-8")
    status["violation"] = re.search(r"^error #\d+", log, re.M) is not None
    status["has_trace"] = (out_dir / "trace.json").exists()

    if a.render and (out_dir / "graph.dot").exists() and shutil.which("dot"):
        try:
            if (out_dir / "graph.dot").stat().st_size < 400_000:
                subprocess.run(["dot", "-Tsvg", str(out_dir / "graph.dot"), "-o", str(out_dir / "graph.svg")],
                               timeout=60)
        except Exception:
            pass

    (case_dir / "status.json").write_text(json.dumps(status, indent=2))
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="work")
    ap.add_argument("--jpf-core", default=os.environ.get("JPF_CORE"), required=not os.environ.get("JPF_CORE"))
    ap.add_argument("--java8-home", default=os.environ.get("JAVA8_HOME"))
    ap.add_argument("--base-jpf", default="base.jpf")
    ap.add_argument("--listener-jar", default="build/TraceDump.jar")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per case")
    ap.add_argument("-j", "--jobs", type=int, default=2)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--render", action="store_true", help="render graph.dot to graph.svg (needs Graphviz)")
    a = ap.parse_args()

    if not Path(a.listener_jar).exists():
        sys.exit(f"{a.listener_jar} not found - run ./build_listener.sh first")
    if not (Path(a.jpf_core) / "build" / "RunJPF.jar").exists():
        sys.exit(f"{a.jpf_core}/build/RunJPF.jar not found - is jpf-core built?")
    base_text = Path(a.base_jpf).read_text(encoding="utf-8")
    if re.search(r"<.*PreciseRaceDetector.*>|#.*listener=<", base_text) and not re.search(r"^\s*listener\s*=", base_text, re.M):
        print("[warn] base.jpf has no active `listener=` line - did you add your race/starvation listeners?")

    v = subprocess.run([exe(a.java8_home, "java"), "-version"], capture_output=True, text=True)
    if '"1.8' not in (v.stderr + v.stdout):
        print("[warn] the java used for JPF does not look like Java 8; jpf-core 8 needs --java8-home")

    cases = sorted(p for p in Path(a.work).iterdir() if (p / "meta.json").exists())
    if a.ids:
        wanted = {re.sub(r"[^\w.-]", "_", i) for i in a.ids}
        cases = [c for c in cases if c.name in wanted]

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        results = []
        for st in ex.map(lambda c: run_case(c, a, base_text), cases):
            print(f"{st['id']:45s} compiled={st['compiled']!s:5} violation={st['violation']!s:5} "
                  f"trace={st['has_trace']!s:5} timeout={st['timed_out']!s:5} {st['seconds']}s")
            results.append(st)

    with open(Path(a.work) / "run_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ["id"])
        w.writeheader()
        w.writerows(results)
    print(f"\n{len(results)} cases; {sum(r['has_trace'] for r in results)} with a counterexample trace. "
          f"Summary: {Path(a.work) / 'run_summary.csv'}")


if __name__ == "__main__":
    main()
