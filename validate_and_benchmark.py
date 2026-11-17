#!/usr/bin/env python3
"""
validate_and_benchmark.py
==========================
Validates LLM-generated Java code with JPF and benchmarks each run.
Uses ONLY the Python standard library + Linux /proc for perf metrics.

Usage (from the jpf_reproduction/ directory):
    # First run – does a full clean build of jpf-core, then validates everything
    python3 validate_and_benchmark.py --codes ../integrated_codes.json --build-once

    # Subsequent runs – skips the clean build (incremental gradle build only)
    python3 validate_and_benchmark.py --codes ../integrated_codes.json
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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────
# 1. CONFIGURATION
# ──────────────────────────────────────────────
JPF_CORE_DIR   = Path("../jpf-core")          # adjust if different
GROUND_TRUTH_CSV = Path("../ground_truth.csv")
RESULTS_FILE   = "validation_results.json"

NUM_PERF_RUNS  = 5          # number of times each code is run for perf
JPF_TIMEOUT_S  = 120        # subprocess timeout (JPF itself has 9 s limit)
BUILD_TIMEOUT_S = 180       # gradle build timeout

JPF_LISTENERS = (
    "gov.nasa.jpf.listener.ThreadCountListener,"
    "gov.nasa.jpf.listener.TimeLimitListener,"
    "gov.nasa.jpf.listener.StarvationListener,"
    "gov.nasa.jpf.listener.PreciseRaceDetector,"
    "gov.nasa.jpf.listener.DeadlockAnalyzer"
)
TIME_LIMIT_MS  = 9000
DEFAULT_DEPTH  = "300"

CLOCK_TICKS = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", 2))


# ──────────────────────────────────────────────
# 2. GROUND-TRUTH LOOKUP  (from ground_truth_lookup.py)
# ──────────────────────────────────────────────
def get_base_problem_name(prompt_title: str) -> str:
    base = re.sub(r"\s+M\d+$", "", prompt_title).strip()
    dot = base.find(".")
    if dot != -1:
        base = base[: dot + 1]
    return base


def load_ground_truth(path: Path) -> Dict[str, str]:
    gt: Dict[str, str] = {}
    if not path.exists():
        print(f"[WARN] ground-truth file not found: {path}")
        return gt
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row.get("Problem Name", "").strip()
            if name:
                gt[name] = row.get("Max Depth", DEFAULT_DEPTH).strip()
    return gt


def lookup_max_depth(prompt_title: str, gt: Dict[str, str]) -> str:
    base = get_base_problem_name(prompt_title)
    raw = gt.get(base, DEFAULT_DEPTH)
    try:
        return str(int(raw) * 10)
    except ValueError:
        return DEFAULT_DEPTH


# ──────────────────────────────────────────────
# 3. RESULT CLASSIFICATION  (from classify_result.py)
# ──────────────────────────────────────────────
def classify_result(jpf_result: str, jpf_details: str) -> str:
    if not jpf_result:
        return "Termination Error"
    r = jpf_result.lower()
    d = jpf_details.lower() if jpf_details else ""

    if "nullpointerexception" in r:
        return "Uncaught Exception"
    if "syntax error" in r:
        return "Compilation Errors"
    if "no static entry method" in r:
        return "No Entry Method"
    if "deadlock" in r:
        return "Deadlock"

    has_results = (
        "====================================================== results" in jpf_result
        or "====================================================== results" in d
    )
    if not has_results:
        return "Termination Error"

    if "preciseracedetector" in r:
        if d and "waiting proportion: 100.00%" in d:
            return "Starvation"
        return "Race Condition"

    if "no errors detected" in r:
        if d:
            if "unique logical threads created during execution: 1" in d:
                return "Single Thread"
            if "waiting proportion: 100.00%" in d:
                return "Starvation"
        return "Pass"

    return "Uncaught Exception"


# ──────────────────────────────────────────────
# 4. JAVA COMPILATION (syntax check via javac)
# ──────────────────────────────────────────────
def compile_java(code: str, class_name: str, tmp_dir: Path) -> Tuple[bool, str]:
    java_file = tmp_dir / f"{class_name}.java"
    java_file.write_text(code, encoding="utf-8")
    try:
        result = subprocess.run(
            ["javac", str(java_file)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "javac timeout"
    except Exception as exc:
        return False, str(exc)
    finally:
        java_file.unlink(missing_ok=True)
        class_file = tmp_dir / f"{class_name}.class"
        class_file.unlink(missing_ok=True)


def extract_class_name(code: str) -> Optional[str]:
    m = re.search(r"\bpublic\s+class\s+(\w+)", code)
    if m:
        return m.group(1)
    m = re.search(r"\bclass\s+(\w+)", code)
    return m.group(1) if m else None


# ──────────────────────────────────────────────
# 5. JPF BUILD & CONFIG
# ──────────────────────────────────────────────
def build_jpf_full(jpf_dir: Path) -> bool:
    """Full clean + build (run once per session)."""
    print("[BUILD] Full clean + buildJar …")
    for cmd in [["./gradlew", "clean"], ["./gradlew", "buildJar"]]:
        try:
            subprocess.run(cmd, cwd=str(jpf_dir),
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           timeout=BUILD_TIMEOUT_S, check=True)
        except Exception as exc:
            print(f"[BUILD] FAILED: {exc}")
            return False
    print("[BUILD] Full build OK")
    return True


def build_jpf_incremental(jpf_dir: Path) -> Tuple[bool, str]:
    """Incremental buildJar (no clean)."""
    try:
        r = subprocess.run(
            ["./gradlew", "buildJar"],
            cwd=str(jpf_dir), capture_output=True, text=True,
            timeout=BUILD_TIMEOUT_S,
        )
        if r.returncode == 0:
            return True, ""
        return False, (r.stdout + r.stderr)[-500:]
    except subprocess.TimeoutExpired:
        return False, "gradle buildJar timeout"
    except Exception as exc:
        return False, str(exc)


def write_source_to_examples(jpf_dir: Path, code: str, class_name: str) -> Path:
    examples = jpf_dir / "src" / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    dest = examples / f"{class_name}.java"
    dest.write_text(code, encoding="utf-8")
    return dest


def create_jpf_config(jpf_dir: Path, class_name: str, max_depth: str) -> Path:
    cfg = jpf_dir / "src" / "examples" / f"{class_name}.jpf"
    cfg.write_text(
        f"target={class_name}\n"
        f"+vm.fast.startup\n"
        f"listener={JPF_LISTENERS}\n"
        f"timeLimitMillis={TIME_LIMIT_MS}\n"
        f"search.depth_limit = {max_depth}\n",
        encoding="utf-8",
    )
    return cfg


def cleanup_examples(jpf_dir: Path, class_name: str) -> None:
    for ext in (".java", ".jpf"):
        f = jpf_dir / "src" / "examples" / f"{class_name}{ext}"
        f.unlink(missing_ok=True)


# ──────────────────────────────────────────────
# 6. JPF EXECUTION
# ──────────────────────────────────────────────
def run_jpf(jpf_dir: Path, class_name: str) -> Tuple[str, str]:
    """Run JPF and return (result_text, details_text)."""
    jpf_bin = jpf_dir / "bin" / "jpf"
    rel_cfg = Path("../src/examples") / f"{class_name}.jpf"
    try:
        r = subprocess.run(
            [str(jpf_bin), str(rel_cfg)],
            cwd=str(jpf_dir / "bin"),
            capture_output=True, text=True,
            timeout=JPF_TIMEOUT_S,
        )
        output = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "timeout", "JPF execution timeout"
    except Exception as exc:
        return "error", f"JPF execution error: {exc}"

    return extract_jpf_result(output), extract_jpf_details(output)


def extract_jpf_result(output: str) -> str:
    m = re.search(
        r"={5,}\s*results\s*\n(.*?)={5,}\s*statistics",
        output, re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip() or "no errors detected"
    lines = [l for l in output.strip().split("\n") if l.strip()]
    if len(lines) <= 10:
        return "\n".join(lines)
    return "\n".join(lines[:5]) + "\n...\n" + "\n".join(lines[-5:])


def extract_jpf_details(output: str) -> str:
    # Grab the full, untruncated exception + stack trace from the "error N"
    # section. This appears BEFORE "results" and is a separate section from
    # it -- it's where JPF actually prints the full exception detail, since
    # the "results" section only ever prints a fixed-length one-line summary.
    error_section = ""
    m = re.search(r"={5,}\s*error\s+\d+\s*\n(.*?)(?=\n={5,})",
                  output, re.DOTALL | re.IGNORECASE)
    if m:
        error_section = "===== full exception (untruncated) =====\n" + m.group(1).strip() + "\n\n"

    lines = output.split("\n")
    for i, line in enumerate(lines):
        if "Unique logical threads created during execution:" in line:
            detail = lines[i:]
            filtered = [l for l in detail if "elapsed time:" not in l.lower()]
            cleaned = [re.sub(r"(search finished):\s+.*", r"\1", l,
                              flags=re.IGNORECASE) for l in filtered]
            return error_section + "\n".join(cleaned).strip()
    tail = lines[-10:] if len(lines) > 10 else lines
    filtered = [l for l in tail if "elapsed time:" not in l.lower()]
    cleaned = [re.sub(r"(search finished):\s+.*", r"\1", l,
                      flags=re.IGNORECASE) for l in filtered]
    return error_section + "\n".join(cleaned).strip()



# ──────────────────────────────────────────────
# 7. PERFORMANCE MEASUREMENT  (Linux /proc only)
# ──────────────────────────────────────────────
def _read_proc_stat_cpu(pid: int) -> int:
    """Return utime+stime in clock ticks from /proc/<pid>/stat."""
    try:
        with open(f"/proc/{pid}/stat", "r") as fh:
            raw = fh.read()
        # skip past "(comm)" which may contain spaces / parens
        after = raw[raw.rfind(")") + 2 :].split()
        utime = int(after[11])   # field 14
        stime = int(after[12])   # field 15
        return utime + stime
    except Exception:
        return 0


def _read_proc_mem_kb(pid: int) -> Tuple[int, int]:
    """Return (VmPeak_kb, VmRSS_kb) from /proc/<pid>/status."""
    vm_peak = 0
    vm_rss  = 0
    try:
        with open(f"/proc/{pid}/status", "r") as fh:
            for line in fh:
                if line.startswith("VmPeak:"):
                    vm_peak = int(line.split()[1])
                elif line.startswith("VmRSS:"):
                    vm_rss = int(line.split()[1])
    except Exception:
        pass
    return vm_peak, vm_rss


def run_jpf_with_perf(jpf_dir: Path, class_name: str) -> Tuple[str, str, dict]:
    """
    Run JPF once, monitoring /proc/<pid> for CPU & memory.
    Returns (jpf_result, jpf_details, perf_dict).
    """
    jpf_bin = jpf_dir / "bin" / "jpf"
    rel_cfg  = Path("../src/examples") / f"{class_name}.jpf"

    wall_start = time.perf_counter()
    try:
        proc = subprocess.Popen(
            [str(jpf_bin), str(rel_cfg)],
            cwd=str(jpf_dir / "bin"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        return "error", f"JPF launch error: {exc}", {}

    pid = proc.pid
    peak_vm  = 0
    peak_rss = 0
    cpu_ticks = 0

    while proc.poll() is None:
        cpu_ticks = _read_proc_stat_cpu(pid)
        vm, rss = _read_proc_mem_kb(pid)
        if vm  > peak_vm:  peak_vm  = vm
        if rss > peak_rss: peak_rss = rss
        time.sleep(0.05)          # poll every 50 ms

    # one final read (process may have just exited)
    cpu_ticks = max(cpu_ticks, _read_proc_stat_cpu(pid))

    stdout, stderr = proc.communicate()
    wall_end = time.perf_counter()
    output = stdout.decode(errors="replace") + stderr.decode(errors="replace")

    wall_s  = round(wall_end - wall_start, 3)
    cpu_s   = round(cpu_ticks / CLOCK_TICKS, 3) if CLOCK_TICKS else 0.0

    perf = {
        "wall_time_s":    wall_s,
        "cpu_time_s":     cpu_s,
        "peak_memory_kb": peak_vm,
        "peak_rss_kb":    peak_rss,
    }
    return extract_jpf_result(output), extract_jpf_details(output), perf


# ──────────────────────────────────────────────
# 8. MAIN ORCHESTRATION
# ──────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="JPF validation + perf benchmark")
    parser.add_argument("--codes", required=True,
                        help="Path to the integrated codes JSON file")
    parser.add_argument("--gt", default=str(GROUND_TRUTH_CSV),
                        help="Path to ground_truth.csv")
    parser.add_argument("--jpf-dir", default=str(JPF_CORE_DIR),
                        help="Path to jpf-core directory")
    parser.add_argument("--runs", type=int, default=NUM_PERF_RUNS,
                        help="Number of performance runs per code")
    parser.add_argument("--build-once", action="store_true",
                        help="Do a full clean+build before starting")
    parser.add_argument("--output", default=RESULTS_FILE,
                        help="Output JSON path")
    args = parser.parse_args()

    jpf_dir = Path(args.jpf_dir).resolve()
    gt_path = Path(args.gt)
    num_runs = args.runs

    # --- sanity checks ---
    if not jpf_dir.exists():
        print(f"[ERROR] jpf-core not found at {jpf_dir}"); sys.exit(1)
    if not (jpf_dir / "bin" / "jpf").exists():
        print(f"[ERROR] JPF binary not found"); sys.exit(1)

    # --- load inputs ---
    with open(args.codes, "r", encoding="utf-8") as fh:
        codes_data = json.load(fh)
    gt_map = load_ground_truth(gt_path)
    print(f"Loaded {len(codes_data)} prompt entries, {len(gt_map)} ground-truth rows")

    # --- optional full build ---
    if args.build_once:
        if not build_jpf_full(jpf_dir):
            print("[ERROR] Full build failed – aborting"); sys.exit(1)

    tmp_dir = Path("/tmp/jpf_validate_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    results: List[dict] = []
    total = 0
    for entry in codes_data:
        total += 4  # gpt, claude, qwen, groq

    done = 0
    for entry in codes_data:
        prompt_id = entry.get("id", 0)
        topic     = entry.get("topic", "")
        max_depth = lookup_max_depth(topic, gt_map)

        for llm_key in ("gpt_code", "claude_code", "qwen_code", "groq_code"):
            done += 1
            llm_name = llm_key.replace("_code", "")
            code = entry.get(llm_key)

            rec: dict = {
                "prompt_id":   prompt_id,
                "topic":       topic,
                "llm":         llm_name,
                "max_depth":   max_depth,
                "code_present": bool(code and code.strip()),
                "code_compiled": False,
                "compile_error": "",
                "jpf_result":   "",
                "jpf_details":  "",
                "classification": "",
                "performance_runs": [],
                "performance_summary": {},
            }

            # ---- skip empty / null code ----
            if not code or not code.strip():
                rec["classification"] = "No Code"
                results.append(rec)
                print(f"[{done}/{total}] {topic} :: {llm_name} – no code, skipped")
                continue

            print(f"[{done}/{total}] {topic} :: {llm_name}  (depth={max_depth})",
                  flush=True)

            # ---- extract class name ----
            class_name = extract_class_name(code)
            if not class_name:
                rec["compile_error"] = "No class declaration found"
                rec["classification"] = "Compilation Errors"
                results.append(rec)
                continue

            # ---- javac syntax check ----
            ok, cerr = compile_java(code, class_name, tmp_dir)
            rec["code_compiled"] = ok
            rec["compile_error"] = cerr
            if not ok:
                rec["jpf_result"] = f"syntax error: {cerr}"
                rec["classification"] = "Compilation Errors"
                results.append(rec)
                print(f"    -> compile error: {cerr[:120]}")
                continue

            # ---- write source into jpf-core/src/examples ----
            write_source_to_examples(jpf_dir, code, class_name)

            # ---- incremental gradle build ----
            bok, blog = build_jpf_incremental(jpf_dir)
            if not bok:
                rec["jpf_result"] = f"syntax error: incremental build failed: {blog}"
                rec["classification"] = "Compilation Errors"
                cleanup_examples(jpf_dir, class_name)
                results.append(rec)
                print(f"    -> gradle build failed")
                continue

            # ---- create .jpf config ----
            create_jpf_config(jpf_dir, class_name, max_depth)

            # ---- run JPF once for the canonical result ----
            jpf_res, jpf_det = run_jpf(jpf_dir, class_name)
            rec["jpf_result"]    = jpf_res
            rec["jpf_details"]   = jpf_det
            rec["classification"] = classify_result(jpf_res, jpf_det)

            # ---- performance runs ----
            perf_runs: List[dict] = []
            for run_idx in range(1, num_runs + 1):
                _, _, perf = run_jpf_with_perf(jpf_dir, class_name)
                perf["run"] = run_idx
                perf_runs.append(perf)

            rec["performance_runs"] = perf_runs

            if perf_runs:
                n = len(perf_runs)
                rec["performance_summary"] = {
                    "num_runs":            n,
                    "avg_wall_time_s":     round(sum(r["wall_time_s"]    for r in perf_runs) / n, 3),
                    "avg_cpu_time_s":      round(sum(r["cpu_time_s"]     for r in perf_runs) / n, 3),
                    "avg_peak_memory_kb":  round(sum(r["peak_memory_kb"] for r in perf_runs) / n, 1),
                    "avg_peak_rss_kb":     round(sum(r["peak_rss_kb"]    for r in perf_runs) / n, 1),
                    "min_wall_time_s":     round(min(r["wall_time_s"]    for r in perf_runs), 3),
                    "max_wall_time_s":     round(max(r["wall_time_s"]    for r in perf_runs), 3),
                }

            # ---- cleanup example files ----
            cleanup_examples(jpf_dir, class_name)

            results.append(rec)
            print(f"    -> {rec['classification']}")

    # ---- write output ----
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nResults written to {output_path.resolve()}")
    print(f"Total entries: {len(results)}")

    # cleanup tmp
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
