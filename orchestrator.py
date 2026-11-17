import csv
import os
import re
import sys
import traceback

from config import PROMPTS_CSV, WORKDIR, RESULTS_DIR, MODELS
from llm_clients import call_llm
from code_extractor import extract_java_code, extract_public_class_name
from compile_check import compile_java
from spotbugs_check import run_spotbugs
from dynamic_check import run_dynamic_checks
from performance_perf import run_performance


def safe_slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def write_report(path: str, topic: str, model_key: str, prompt: str,
                  raw_response: str, code: str, class_name: str,
                  compile_ok: bool, compile_log: str,
                  spotbugs_verdict: str, spotbugs_findings: list, spotbugs_log: str,
                  dynamic_result: dict,
                  perf: dict, error: str = None):
    with open(path, "w") as f:
        f.write(f"TOPIC: {topic}\n")
        f.write(f"MODEL: {model_key} ({MODELS[model_key]['model_id']})\n")
        f.write("=" * 70 + "\n\n")

        if error:
            f.write(f"PIPELINE ERROR: {error}\n")
            return

        f.write("[COMPILATION]\n")
        f.write(f"status: {'SUCCESS' if compile_ok else 'FAILED'}\n")
        if not compile_ok:
            f.write(f"log:\n{compile_log}\n")
        f.write("\n")

        f.write("[STATIC CONCURRENCY ANALYSIS - SpotBugs]\n")
        f.write(f"verdict: {spotbugs_verdict}\n")
        f.write("(NO_FINDINGS = no MT_CORRECTNESS bug patterns matched; FINDINGS_PRESENT = one or\n"
                " more candidate concurrency antipatterns found -- heuristic, review manually, not\n"
                " a sound/complete verifier; SPOTBUGS_FAILED = tool error, check SPOTBUGS_HOME config)\n")
        if spotbugs_findings:
            f.write("findings:\n")
            for finding in spotbugs_findings:
                f.write(f"  - {finding}\n")
        f.write("\n")

        f.write("[DYNAMIC CHECKS - deadlock / uncaught exception / output consistency]\n")
        if dynamic_result:
            f.write(f"verdict: {dynamic_result['verdict']}\n")
            f.write("(CLEAN = no issues across repeated runs; DEADLOCK_DETECTED = jstack confirmed a real\n"
                    " deadlock; UNCAUGHT_EXCEPTION = an exception escaped main(); HANG_NO_DEADLOCK_CONFIRMED =\n"
                    " run timed out but jstack found no deadlock, could be slow/looping code, not conclusive;\n"
                    " INCONSISTENT_OUTPUT = repeated runs produced different stdout, may indicate a race or may\n"
                    " be expected thread-interleaving nondeterminism -- review manually)\n")
            f.write(f"reps: {dynamic_result['reps']}, deadlock_runs: {dynamic_result['deadlock_runs']}, "
                    f"exception_runs: {dynamic_result['exception_runs']}, "
                    f"hang_no_deadlock_runs: {dynamic_result['hang_no_deadlock_runs']}, "
                    f"distinct_output_count: {dynamic_result['distinct_output_count']}\n")
            if dynamic_result.get("sample_deadlock_log"):
                f.write("sample deadlock thread dump:\n")
                f.write(dynamic_result["sample_deadlock_log"] + "\n")
            if dynamic_result.get("sample_exception_stderr"):
                f.write("sample uncaught exception stderr:\n")
                f.write(dynamic_result["sample_exception_stderr"] + "\n")
            if dynamic_result.get("sample_launch_failure_stderr"):
                f.write("sample launch failure stderr:\n")
                f.write(dynamic_result["sample_launch_failure_stderr"] + "\n")
        else:
            f.write("not run (compilation failed)\n")
        f.write("\n")

        f.write("[PERFORMANCE]\n")
        if perf:
            for k, v in perf.items():
                if k == "raw_logs":
                    continue
                f.write(f"{k}: {v}\n")
        else:
            f.write("not measured (compilation failed)\n")
        f.write("\n")

        f.write("[GENERATED CODE]\n")
        f.write(code + "\n\n")

        f.write("[RAW SPOTBUGS LOG]\n")
        f.write(spotbugs_log + "\n")


def process_one(topic: str, prompt: str, model_key: str):
    prompt_slug = safe_slug(topic)
    prompt_workdir = os.path.join(WORKDIR, prompt_slug, model_key)
    os.makedirs(prompt_workdir, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, f"{prompt_slug}__{model_key}.txt")

    try:
        raw_response = call_llm(model_key, prompt)
    except Exception as e:
        write_report(report_path, topic, model_key, prompt, "", "", "",
                     False, "", "N/A", [], "", None, None, error=f"LLM call failed: {e}")
        return

    code = extract_java_code(raw_response)
    try:
        class_name = extract_public_class_name(code)
    except Exception as e:
        write_report(report_path, topic, model_key, prompt, raw_response, code, "",
                     False, "", "N/A", [], "", None, None, error=f"Could not parse class name: {e}")
        return

    compile_ok, compile_log = compile_java(code, class_name, prompt_workdir)
    if not compile_ok:
        write_report(report_path, topic, model_key, prompt, raw_response, code, class_name,
                     False, compile_log, "N/A", [], "", None, None)
        return

    spotbugs_verdict, spotbugs_findings, spotbugs_log = run_spotbugs(class_name, prompt_workdir)
    dynamic_result = run_dynamic_checks(class_name, prompt_workdir)
    perf = run_performance(class_name, prompt_workdir)

    write_report(report_path, topic, model_key, prompt, raw_response, code, class_name,
                 True, compile_log, spotbugs_verdict, spotbugs_findings, spotbugs_log,
                 dynamic_result, perf)


def main():
    os.makedirs(WORKDIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(PROMPTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows) * len(MODELS)
    done = 0
    for row in rows:
        topic, prompt = row["Topic"], row["Prompt"]
        for model_key in MODELS:
            done += 1
            print(f"[{done}/{total}] {topic} :: {model_key}", flush=True)
            try:
                process_one(topic, prompt, model_key)
            except Exception:
                print(f"  !! unexpected failure, see traceback below", file=sys.stderr)
                traceback.print_exc()

    print("Done. Reports in:", RESULTS_DIR)


if __name__ == "__main__":
    main()
