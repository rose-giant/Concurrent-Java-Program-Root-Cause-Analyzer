"""
Reproduces CONCUR's evaluation methodology as closely as the uploaded source
allows: LLM generation -> javac syntax check -> write into jpf-core/src/examples
-> incremental gradle build -> JPF verification with the paper's exact listener
stack and per-problem depth calibration -> classify_result() taxonomy.

Run from the pipeline/ directory:
    python3 jpf_reproduction/run_concur_validation.py --build-once
    python3 jpf_reproduction/run_concur_validation.py   (subsequent runs, skips full rebuild)

Deviations from the literal uploaded scripts, and why:
  - build_jpf_project() (full `gradlew clean` + `buildJar`) is called ONCE at
    the start of a session (--build-once), not per generated program. Calling
    it per-program would mean a multi-minute full jpf-core rebuild for each of
    ~460 programs (~a day of wall-clock time). Subsequent programs use
    build_jar_incremental() (`buildJar` without `clean`), which recompiles only
    the changed example file. Verified in this session: --build-once produces
    the same jpf.jar (major version 52, all 3 custom listeners present).
  - k (generations per prompt) defaults to 1. Set K_GENERATIONS to 3 to
    reproduce the paper's pass@3 metric; each generation makes a fresh LLM
    call, so this roughly triples LLM API usage.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # pipeline/ root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                   # jpf_reproduction/

from llm_clients import call_llm
from code_extractor import extract_java_code
from config import MODELS

from jpf_validator_v4 import JPFValidatorV4
from ground_truth_lookup import load_ground_truth, lookup_max_depth
from classify_result import classify_result

# ---------------------------------------------------------------------------
PROMPTS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts.csv")
GROUND_TRUTH_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ground_truth.csv")
# JPF_CORE_DIR = os.path.expanduser("../")   # EDIT if different on your machine
JPF_CORE_DIR = os.path.expanduser("~/jpf/jpf-core") # Updated to match your directory
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results_concur")
GENERATED_CODE_JSON = os.path.join(RESULTS_DIR, "generated_code.json")

K_GENERATIONS = 1   # set to 3 to reproduce pass@3
# ---------------------------------------------------------------------------


def load_existing_results():
    if os.path.exists(GENERATED_CODE_JSON):
        with open(GENERATED_CODE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(data):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(GENERATED_CODE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def validate_one(validator: JPFValidatorV4, code: str, max_depth: str):
    """
    Runs the full compile -> write -> incremental build -> JPF -> classify
    pipeline for a single generated code string. Returns a dict with all
    intermediate results for the report.
    """
    class_name = validator.extract_class_name(code)
    if not class_name:
        return {
            "class_name": None,
            "compiled": False,
            "compile_error": "No class declaration found in generated code",
            "jpf_result": "syntax error: no class declaration",
            "jpf_details": "",
            "label": classify_result("syntax error: no class declaration", ""),
        }

    compiled, compile_err = validator.compile_java_code(code, class_name)
    if not compiled:
        jpf_result = f"syntax error: {compile_err}"
        return {
            "class_name": class_name,
            "compiled": False,
            "compile_error": compile_err,
            "jpf_result": jpf_result,
            "jpf_details": "",
            "label": classify_result(jpf_result, ""),
        }

    # Write into jpf-core/src/examples and rebuild incrementally
    validator.write_source_to_examples(code, class_name)
    build_ok, build_log = validator.build_jar_incremental()
    if not build_ok:
        jpf_result = f"syntax error: incremental build failed: {build_log[-500:]}"
        return {
            "class_name": class_name,
            "compiled": False,
            "compile_error": build_log[-500:],
            "jpf_result": jpf_result,
            "jpf_details": "",
            "label": classify_result(jpf_result, ""),
        }

    validator.create_jpf_config(class_name, max_depth)
    jpf_result, jpf_details = validator.run_jpf(class_name)
    label = classify_result(jpf_result, jpf_details)

    return {
        "class_name": class_name,
        "compiled": True,
        "compile_error": "",
        "jpf_result": jpf_result,
        "jpf_details": jpf_details,
        "label": label,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-once", action="store_true",
                         help="Run a full `gradlew clean buildJar` before starting (do this on first run)")
    parser.add_argument("--models", nargs="*", default=list(MODELS.keys()),
                         help="Subset of MODELS keys from config.py to run (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Only process the first N prompt rows (for smoke testing)")
    args = parser.parse_args()

    validator = JPFValidatorV4(generated_code_dir=RESULTS_DIR, jpf_core_dir=JPF_CORE_DIR)
    validator.setup_directories()

    if args.build_once:
        print("Running full clean+buildJar (this takes several minutes)...")
        if not validator.build_jpf_project():
            print("FATAL: full build failed, aborting.")
            sys.exit(1)

    gt_map = load_ground_truth(GROUND_TRUTH_CSV)
    print(f"Loaded {len(gt_map)} ground-truth entries for depth calibration")

    with open(PROMPTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    results = load_existing_results()
    results_by_key = {(r["prompt_title"], r.get("model")): r for r in results}

    total = len(rows) * len(args.models)
    done = 0

    for row in rows:
        topic, prompt = row["Topic"], row["Prompt"]
        max_depth = lookup_max_depth(topic, gt_map)

        for model_key in args.models:
            done += 1
            key = (topic, model_key)
            entry = results_by_key.get(key)
            if entry and len(entry.get("code_list", [])) >= K_GENERATIONS:
                print(f"[{done}/{total}] {topic} :: {model_key} -- already have {K_GENERATIONS} versions, skipping")
                continue

            print(f"[{done}/{total}] {topic} :: {model_key} (max_depth={max_depth})", flush=True)

            if entry is None:
                entry = {
                    "prompt_title": topic, "model": model_key, "prompt_content": prompt,
                    "code_list": [], "llm_output": [], "jpf_result": [], "jpf_details": [],
                    "label": [], "max_depth": max_depth,
                }
                results.append(entry)
                results_by_key[key] = entry

            while len(entry["code_list"]) < K_GENERATIONS:
                try:
                    raw = call_llm(model_key, prompt)
                except Exception as e:
                    entry["code_list"].append("")
                    entry["llm_output"].append(f"LLM call failed: {e}")
                    entry["jpf_result"].append("")
                    entry["jpf_details"].append("")
                    entry["label"].append("Termination Error")
                    continue

                code = extract_java_code(raw)
                outcome = validate_one(validator, code, max_depth)

                entry["code_list"].append(code)
                entry["llm_output"].append(raw)
                entry["jpf_result"].append(outcome["jpf_result"])
                entry["jpf_details"].append(outcome["jpf_details"])
                entry["label"].append(outcome["label"])

                print(f"    -> {outcome['label']}")

            entry["pass@1"] = 1.0 if entry["label"] and entry["label"][0] == "Pass" else 0.0
            passes = sum(1 for l in entry["label"] if l == "Pass")
            entry["pass@3"] = passes / len(entry["label"]) if entry["label"] else 0.0

            save_results(results)  # incremental save after every prompt/model, like the original

    print("Done. Results in:", GENERATED_CODE_JSON)


if __name__ == "__main__":
    main()
