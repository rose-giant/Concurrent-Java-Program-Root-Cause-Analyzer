import csv
import os
import re
import sys
import traceback

from config import PROMPTS_CSV, WORKDIR, RESULTS_DIR, MODELS
from llm_clients import call_llm
from code_extractor import extract_java_code, extract_public_class_name
from correctness_jpf import compile_java, run_jpf
from performance_perf import run_performance


def safe_slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def write_report(path: str, topic: str, model_key: str, prompt: str,
                  raw_response: str, code: str, class_name: str,
                  compile_ok: bool, compile_log: str,
                  jpf_verdict: str, jpf_log: str,
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

        f.write("[CORRECTNESS - JPF concurrency check]\n")
        f.write(f"verdict: {jpf_verdict}\n")
        f.write("(NO_ERRORS_FOUND = no deadlock/data-race/uncaught-exception found by JPF within search bounds;\n"
                " ERRORS_FOUND = JPF found a defect; TIMEOUT = search did not finish; "
                "JPF_FAILED = JPF itself errored/misconfigured)\n\n")

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

        f.write("[RAW JPF LOG]\n")
        f.write(jpf_log + "\n")


def process_one(topic: str, prompt: str, model_key: str):
    prompt_slug = safe_slug(topic)
    prompt_workdir = os.path.join(WORKDIR, prompt_slug, model_key)
    os.makedirs(prompt_workdir, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, f"{prompt_slug}__{model_key}.txt")

    try:
        raw_response = call_llm(model_key, prompt)
    except Exception as e:
        write_report(report_path, topic, model_key, prompt, "", "", "",
                     False, "", "N/A", "", None, error=f"LLM call failed: {e}")
        return

    code = extract_java_code(raw_response)
    try:
        class_name = extract_public_class_name(code)
    except Exception as e:
        write_report(report_path, topic, model_key, prompt, raw_response, code, "",
                     False, "", "N/A", "", None, error=f"Could not parse class name: {e}")
        return

    compile_ok, compile_log = compile_java(code, class_name, prompt_workdir)
    if not compile_ok:
        write_report(report_path, topic, model_key, prompt, raw_response, code, class_name,
                     False, compile_log, "N/A", "", None)
        return

    jpf_verdict, jpf_log = run_jpf(class_name, prompt_workdir)
    perf = run_performance(class_name, prompt_workdir)

    write_report(report_path, topic, model_key, prompt, raw_response, code, class_name,
                 True, compile_log, jpf_verdict, jpf_log, perf)


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
