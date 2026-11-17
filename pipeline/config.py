"""
Central configuration for the concurrency-benchmark pipeline.
Edit the paths/env-var names below to match your machine.
"""

import os

# ---------------------------------------------------------------------------
# Paths (EDIT THESE for your machine)
# ---------------------------------------------------------------------------
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
# "gpt" and "claude" go through AvalAI (https://avalai.ir), a proxy that
# exposes real GPT and Claude models behind one OpenAI-compatible endpoint --
# see call_avalai() in llm_clients.py. Both slots share the single
# AVALAI_API_KEY env var; only the model_id differs per slot.
# Verify current model IDs at https://docs.avalai.ir/en/models/ before running,
# names/availability change.
# ---------------------------------------------------------------------------
MODELS = {
    "groq":   {"provider": "groq", "api_key_env": "GROQ_API_KEY", "model_id": "groq/compound"},
    "gpt":    {"provider": "avalai", "api_key_env": "AVALAI_API_KEY", "model_id": "gpt-5.4"},
    "claude": {"provider": "avalai", "api_key_env": "AVALAI_API_KEY", "model_id": "claude-sonnet-5"},
    # "gemini": {"provider": "google",    "api_key_env": "GOOGLE_API_KEY",    "model_id": "gemini-2.5-flash"},
    "qwen": {"provider": "dashscope", "api_key_env": "QWEN_API_KEY", "model_id": "qwen3.8-max"},
}

# AvalAI's single OpenAI-compatible endpoint, used for both "gpt" and "claude"
# slots above (just a different model_id per call).
AVALAI_BASE_URL = "https://api.avalai.ir/v1"

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
