import argparse
import csv
import json
import os
import requests

MODEL = "qwen3.8-max"
API_KEY = os.environ["QWEN_API_KEY"]

# DashScope's OpenAI-compatible endpoint. Use the "-intl" host if your account/key
# is provisioned outside mainland China; switch to the non-intl host otherwise.
API_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"


def parse_args():
    parser = argparse.ArgumentParser(description="Run a range of prompts from prompts.csv through Qwen.")
    parser.add_argument("--start", type=int, default=1, help="First prompt number to run (1-indexed, inclusive). Default: 1")
    parser.add_argument("--end", type=int, default=None, help="Last prompt number to run (1-indexed, inclusive). Default: run to end of file")
    parser.add_argument("--prompts-file", type=str, default="prompts.csv", help="Path to the prompts CSV. Default: prompts.csv")
    parser.add_argument("--output-file", type=str, default="qwen_results.json", help="Path to write results JSON. Default: qwen_results.json")
    return parser.parse_args()


def call_qwen(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    return resp


def main():
    args = parse_args()

    results = []

    with open(args.prompts_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=1):
            if i < args.start:
                continue
            if args.end is not None and i > args.end:
                break  # rows are in order, so nothing left to do past --end

            prompt = row["Prompt"].strip()

            if not prompt:
                continue

            print(f"Running prompt {i}...")

            resp = call_qwen(prompt)

            if resp.status_code != 200:
                print(f"ERROR on prompt {i}: {resp.status_code} - {resp.text}")
                continue

            data = resp.json()
            answer = data["choices"][0]["message"]["content"]

            results.append({
                "prompt_number": i,
                "prompt": prompt,
                "response": answer
            })

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Saved {len(results)} results to {args.output_file}")


if __name__ == "__main__":
    main()