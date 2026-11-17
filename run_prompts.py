#!/usr/bin/env python3
"""
Sends every prompt in prompts.csv to GPT-5 (via the AvalAI OpenAI-compatible
REST API) and stores the results in a JSON file. Uses only `requests` -- no
openai package needed.

Setup:
    pip install requests
    export AVALAI_API_KEY="your-key-here"

Usage:
    python3 run_prompts.py prompts.csv results.json

If results.json already exists, already-answered rows are skipped, so you can
safely re-run the script after an interruption to pick up where it left off.
"""

import csv
import json
import os
import re
import sys
import time

import requests

MODEL = "gpt-5.4"  # AvalAI does not expose a plain "gpt-5" - see https://docs.avalai.ir/en/models/
API_URL = "https://api.avalai.ir/v1/chat/completions"
MAX_RETRIES = 8
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 120
DELAY_BETWEEN_REQUESTS_SECONDS = 10  # be gentle on rate limits; raise if you still hit 429s


def load_existing_results(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_results(path, results):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def call_model(api_key, prompt):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if resp.status_code == 429:
                # Rate limited - prefer Retry-After header; fall back to parsing
                # "try again in Xs" from the JSON error body; else exponential backoff.
                retry_after = resp.headers.get("Retry-After")
                wait = None
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = None
                if wait is None:
                    try:
                        msg = resp.json().get("error", {}).get("message", "")
                        match = re.search(r"in\s+([\d.]+)s", msg)
                        if match:
                            wait = float(match.group(1))
                    except Exception:  # noqa: BLE001
                        pass
                if wait is None:
                    wait = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                wait += 1  # small buffer so we don't retry a hair too early
                print(f"    rate limited (429), waiting {wait:.0f}s before retry "
                      f"({attempt}/{MAX_RETRIES})...", file=sys.stderr)
                time.sleep(wait)
                last_error = RuntimeError("429 Too Many Requests")
                continue
            if not resp.ok:
                # Surface the API's actual error message, not just the HTTP status.
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"    attempt {attempt}/{MAX_RETRIES} failed: {exc}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"All retries failed: {last_error}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_prompts.py <prompts.csv> [results.json]", file=sys.stderr)
        sys.exit(1)

    csv_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "results.json"

    api_key = os.environ.get("AVALAI_API_KEY")
    if not api_key:
        print("ERROR: environment variable AVALAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
    api_key = api_key.strip()  # guard against trailing newline/whitespace in the env var

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    results = load_existing_results(out_path)
    done_topics = {r["topic"] for r in results}

    print(f"Loaded {len(rows)} prompts. {len(done_topics)} already done.")

    for i, row in enumerate(rows, start=1):
        topic = row.get("Topic", f"row_{i}")
        prompt = row.get("Prompt", "")

        if topic in done_topics:
            continue

        print(f"[{i}/{len(rows)}] Sending: {topic}")
        try:
            answer = call_model(api_key, prompt)
            results.append({
                "topic": topic,
                "prompt": prompt,
                "response": answer,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED permanently: {exc}", file=sys.stderr)
            results.append({
                "topic": topic,
                "prompt": prompt,
                "response": None,
                "error": str(exc),
            })

        # save after every prompt so progress isn't lost on interruption
        save_results(out_path, results)

        # small delay between requests to avoid tripping rate limits
        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    print(f"Done. Results saved to {out_path}")


if __name__ == "__main__":
    main()
