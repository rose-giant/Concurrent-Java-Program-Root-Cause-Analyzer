#!/usr/bin/env python3
"""
validate_codes.py
==================
Generic version of validate_and_benchmark.py / validate_claude_range.py /
validate_qwen_range.py: same JPF validation pipeline (javac syntax check ->
write into jpf-core/src/examples -> incremental gradle build -> JPF run with
the paper's listener stack -> classify_result taxonomy), but works on ANY
flat JSON list of code entries instead of hard-coding one particular key
layout.

It auto-detects, per entry, whichever of these keys is present:
    id field:    "id" | "prompt_id"
    code field:  "new_code" | "code" | "code_base"
    topic field: "topic" | "filename" | "title"          (optional)

So it works directly on:
    - the merged json you get from combining several Qwen_json_*.json files
      (entries shaped like {"id": 1, "new_code": "..."} )
    - qwen_all.json-style entries ({"id": ..., "topic": ..., "code": ...})
    - merged_code.json-style Claude entries
      ({"prompt_id": ..., "filename": ..., "code_base": ...})

Output naming
-------------
By default the output file is named after the INPUT file:
    <input_stem>_jpf_results.json
e.g. `merged.json` -> `merged_jpf_results.json`
Override with --output if you want a different name.

Usage (run from the jpf_reproduction/ directory — note jpf-core itself is
TWO levels up from here: jpf_reproduction/ -> pipeline/ -> jpf-core/, same
as validate_claude_range.py / validate_qwen_range.py):

    # First run this session - full clean build of jpf-core
    python3 validate_codes.py --codes ../../qwen_repaired.json \\
        --jpf-dir ../../ --gt ../../ground_truth.csv --build-once --llm-name qwen

    # Subsequent runs this session - skip the clean build
    python3 validate_codes.py --codes ../../qwen_repaired.json \\
        --jpf-dir ../../ --gt ../../ground_truth.csv --llm-name qwen

    # Optional: filter to an id range, or pick a custom output filename
    python3 validate_codes.py --codes ../../qwen_repaired.json \\
        --jpf-dir ../../ --gt ../../ground_truth.csv \\
        --id-min 1 --id-max 50 --llm-name qwen --output my_results.json

Note: if your codes JSON lives directly in jpf-core/ (one level up, like
../integrated_codes.json in the older scripts) rather than in pipeline/
(two levels up), adjust --codes/--gt accordingly — only --jpf-dir must
point at the jpf-core folder itself (the one containing bin/, gradlew, src/).
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────
# 1. CONFIGURATION (unchanged from the other validate_*.py scripts)
# ──────────────────────────────────────────────
JPF_TIMEOUT_S = 120
BUILD_TIMEOUT_S = 180

JPF_LISTENERS = (
    "gov.nasa.jpf.listener.ThreadCountListener,"
    "gov.nasa.jpf.listener.TimeLimitListener,"
    "gov.nasa.jpf.listener.StarvationListener,"
    "gov.nasa.jpf.listener.PreciseRaceDetector,"
    "gov.nasa.jpf.listener.DeadlockAnalyzer"
)
TIME_LIMIT_MS = 9000
DEFAULT_DEPTH = "300"

# Keys tried in order, per entry, to find the id / code / topic.
ID_KEYS = ("id", "prompt_id")
CODE_KEYS = ("new_code", "code", "code_base")
TOPIC_KEYS = ("topic", "filename", "title")


def get_entry_id(entry: dict) -> Optional[int]:
    for k in ID_KEYS:
        if k in entry and entry[k] is not None:
            try:
                return int(entry[k])
            except (TypeError, ValueError):
                return entry[k]
    return None


def get_entry_code(entry: dict) -> str:
    for k in CODE_KEYS:
        if k in entry and entry[k]:
            return entry[k]
    return ""


def get_entry_topic(entry: dict) -> str:
    for k in TOPIC_KEYS:
        if k in entry and entry[k]:
            return entry[k]
    return ""


# ──────────────────────────────────────────────
# 2. GROUND-TRUTH LOOKUP (verbatim from ground_truth_lookup.py)
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
# 3. RESULT CLASSIFICATION (verbatim from classify_result.py)
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
# 7. MAIN ORCHESTRATION
# ──────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="JPF validation for any flat codes JSON "
                    "(auto-detects id/code/topic keys); "
                    "output defaults to <input_stem>_jpf_results.json")
    parser.add_argument("--codes", required=True,
                         help="Path to the codes JSON (list of entries, each "
                              "with an id/prompt_id and new_code/code/code_base)")
    parser.add_argument("--gt", default="../../ground_truth.csv",
                         help="Path to ground_truth.csv (default: ../../ground_truth.csv, "
                              "i.e. jpf-core/ground_truth.csv from jpf_reproduction/)")
    parser.add_argument("--jpf-dir", default="../../",
                         help="Path to jpf-core directory itself — the one containing "
                              "bin/, gradlew, src/ (default: ../../, i.e. two levels up "
                              "from jpf_reproduction/)")
    parser.add_argument("--llm-name", default="unknown",
                         help="Value to tag every result record with under \"llm\" "
                              "(default: unknown)")
    parser.add_argument("--id-min", type=int, default=None,
                         help="Lowest id to process (default: no lower bound)")
    parser.add_argument("--id-max", type=int, default=None,
                         help="Highest id to process, inclusive (default: no upper bound)")
    parser.add_argument("--build-once", action="store_true",
                         help="Do a full clean+build before starting (do this once per session)")
    parser.add_argument("--output", default=None,
                         help="Output JSON path (default: <input_stem>_jpf_results.json, "
                              "written alongside the current directory)")
    args = parser.parse_args()

    codes_path = Path(args.codes)
    jpf_dir = Path(args.jpf_dir).resolve()
    gt_path = Path(args.gt)

    # ---- derive default output filename from the input filename ----
    output_path = Path(args.output) if args.output else Path(f"{codes_path.stem}_jpf_results.json")

    # ---- sanity checks ----
    if not codes_path.exists():
        print(f"[ERROR] codes file not found: {codes_path}"); sys.exit(1)
    if not jpf_dir.exists():
        print(f"[ERROR] jpf-core not found at {jpf_dir}"); sys.exit(1)
    if not (jpf_dir / "bin" / "jpf").exists():
        print(f"[ERROR] JPF binary not found at {jpf_dir / 'bin' / 'jpf'}")
        print("        --jpf-dir must point at the jpf-core folder itself. "
              "From jpf_reproduction/ that is usually ../../ (two levels up), "
              "not ../ (which only reaches pipeline/).")
        sys.exit(1)
    if not (jpf_dir / "gradlew").exists():
        print(f"[ERROR] gradlew not found at {jpf_dir / 'gradlew'} — is --jpf-dir correct?"); sys.exit(1)

    with open(codes_path, "r", encoding="utf-8") as fh:
        all_entries = json.load(fh)
    gt_map = load_ground_truth(gt_path)

    entries = []
    for e in all_entries:
        eid = get_entry_id(e)
        if args.id_min is not None and (eid is None or eid < args.id_min):
            continue
        if args.id_max is not None and (eid is None or eid > args.id_max):
            continue
        entries.append(e)
    entries.sort(key=lambda e: (get_entry_id(e) is None, get_entry_id(e)))

    print(f"Loaded {len(all_entries)} total entries, {len(entries)} selected "
          f"(id range [{args.id_min}, {args.id_max}]); {len(gt_map)} ground-truth rows")
    print(f"Output will be written to: {output_path.resolve()}")

    if args.build_once:
        if not build_jpf_full(jpf_dir):
            print("[ERROR] Full build failed – aborting"); sys.exit(1)

    tmp_dir = Path("/tmp/jpf_validate_generic_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    results: List[dict] = []
    total = len(entries)

    for done, entry in enumerate(entries, start=1):
        prompt_id = get_entry_id(entry)
        topic = get_entry_topic(entry)
        code = get_entry_code(entry)
        max_depth = lookup_max_depth(topic, gt_map)

        rec: dict = {
            "prompt_id": prompt_id,
            "topic": topic,
            "llm": args.llm_name,
            "max_depth": max_depth,
            "code_present": bool(code and code.strip()),
            "code_compiled": False,
            "compile_error": "",
            "jpf_result": "",
            "jpf_details": "",
            "classification": "",
        }

        label = topic if topic else f"id {prompt_id}"
        print(f"[{done}/{total}] id={prompt_id} {label} (depth={max_depth})", flush=True)

        if not code or not code.strip():
            rec["classification"] = "No Code"
            results.append(rec)
            print("    -> no code, skipped")
            continue

        class_name = extract_class_name(code)
        if not class_name:
            rec["compile_error"] = "No class declaration found"
            rec["classification"] = "Compilation Errors"
            results.append(rec)
            print("    -> no class declaration")
            continue

        ok, cerr = compile_java(code, class_name, tmp_dir)
        rec["code_compiled"] = ok
        rec["compile_error"] = cerr
        if not ok:
            rec["jpf_result"] = f"syntax error: {cerr}"
            rec["classification"] = "Compilation Errors"
            results.append(rec)
            print(f"    -> compile error: {cerr[:120]}")
            continue

        write_source_to_examples(jpf_dir, code, class_name)

        bok, blog = build_jpf_incremental(jpf_dir)
        if not bok:
            rec["jpf_result"] = f"syntax error: incremental build failed: {blog}"
            rec["classification"] = "Compilation Errors"
            cleanup_examples(jpf_dir, class_name)
            results.append(rec)
            print("    -> gradle build failed")
            continue

        create_jpf_config(jpf_dir, class_name, max_depth)

        jpf_res, jpf_det = run_jpf(jpf_dir, class_name)
        rec["jpf_result"] = jpf_res
        rec["jpf_details"] = jpf_det
        rec["classification"] = classify_result(jpf_res, jpf_det)

        cleanup_examples(jpf_dir, class_name)

        results.append(rec)
        print(f"    -> {rec['classification']}")

        # incremental save after every entry, in case of a crash/timeout later
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nResults written to {output_path.resolve()}")
    print(f"Total entries: {len(results)}")

    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
