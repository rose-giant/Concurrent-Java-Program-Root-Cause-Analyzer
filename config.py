"""
Central configuration for the concurrency-benchmark pipeline.
Edit the paths/env-var names below to match your machine.
"""

import os

# ---------------------------------------------------------------------------
# Paths (EDIT THESE for your machine)
# ---------------------------------------------------------------------------
LIARA_API_BASE = "https://ai.liara.ir/api/6a8eb06f44cd5019436110af/v1"
PROMPTS_CSV = "prompts.csv"          # Topic,Prompt columns
WORKDIR = "work"                     # scratch dir for generated .java / .class files
RESULTS_DIR = "results"              # one .txt per (prompt, LLM)

JDK_BIN = ""                         # e.g. "/usr/lib/jvm/jdk-8/bin/" (must end with / or be empty for PATH default)
JAVAC = os.path.join(JDK_BIN, "javac") if JDK_BIN else "javac"
JAVA = os.path.join(JDK_BIN, "java") if JDK_BIN else "java"
JSTACK = os.path.join(JDK_BIN, "jstack") if JDK_BIN else "jstack"

GNU_TIME_CMD = "/usr/bin/time"       # GNU time (needs -v support). `sudo apt install time` if missing.

# SpotBugs distribution root (the dir containing bin/spotbugs after unzipping
# a release from https://github.com/spotbugs/spotbugs/releases). Static
# analysis only -- doesn't execute the code, so no JDK-version conflicts.
SPOTBUGS_HOME = ""                   # e.g. "/opt/spotbugs-4.8.6"
SPOTBUGS_CMD = [os.path.join(SPOTBUGS_HOME, "bin", "spotbugs")] if SPOTBUGS_HOME else ["spotbugs"]

# ---------------------------------------------------------------------------
# LLMs to evaluate. Each entry: provider tag -> (env var for API key, model id)
#
# NOTE: gpt5 and claude are substituted with free open-weight models served
# via Groq (no reliable free tier exists for real GPT-5 / Claude API access).
# These are NOT the actual GPT-5 / Claude models -- relabel honestly in your
# writeup, e.g. "GPT-OSS-120B" and "Llama-3.3-70B", not "GPT-5" / "Claude".
# Verify current model IDs at https://console.groq.com/docs/models before running,
# names/availability change.
# ---------------------------------------------------------------------------
MODELS = {
    "groq":   {"provider": "groq", "api_key_env": "GROQ_API_KEY", "model_id": "groq/compound"},
    "gpt5":   {"provider": "liara", "api_key_env": "LIARA_API_KEY", "model_id": "openai/gpt-5.4-mini"},
    "claude": {"provider": "liara", "api_key_env": "LIARA_API_KEY", "model_id": "anthropic/claude-sonnet-4.5"},
    "gemini": {"provider": "liara", "api_key_env": "LIARA_API_KEY", "model_id": "google/gemini-2.5-pro"},
    "qwen": {"provider": "dashscope", "api_key_env": "QWEN_API_KEY", "model_id": "qwen3.8-max"},
}

# Groq free tier is rate-limited per model: ~30 requests/min, ~6,000 tokens/min,
# ~1,000 requests/day (shared across both "gpt5" and "claude" slots above since
# they're both Groq -- so effectively ~500 requests/day each if run same-day).
# The orchestrator sleeps between Groq calls to stay under the per-minute caps.
GROQ_MIN_SECONDS_BETWEEN_CALLS = 3

# ---------------------------------------------------------------------------
# Execution limits
# ---------------------------------------------------------------------------
LLM_TIMEOUT_SEC = 120
COMPILE_TIMEOUT_SEC = 60
PERF_TIMEOUT_SEC = 30          # per single execution of the generated program
PERF_REPETITIONS = 20          # how many times to run each program for throughput measurement

SPOTBUGS_TIMEOUT_SEC = 60

DYNAMIC_CHECK_REPS = 5          # separate, smaller run set dedicated to deadlock/crash/consistency checks
DYNAMIC_CHECK_TIMEOUT_SEC = 15  # if a run exceeds this, treat as hang -> take a thread dump before killing
