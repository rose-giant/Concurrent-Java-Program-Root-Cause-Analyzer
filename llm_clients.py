"""
Thin, uniform wrappers around each provider's completion endpoint.
Each function takes a prompt string and returns the raw text response.

Requires: pip install requests
"""

import os
import time
import requests
from config import MODELS, LLM_TIMEOUT_SEC, GROQ_MIN_SECONDS_BETWEEN_CALLS

_last_groq_call = 0.0


def _get_key(model_key: str) -> str:
    env_var = MODELS[model_key]["api_key_env"]
    key = os.environ.get(env_var)
    if not key:
        raise RuntimeError(f"Missing API key: set env var {env_var} for '{model_key}'")
    return key


def _raise_with_body(resp):
    """requests' raise_for_status() discards the response body, which is where
    the actual reason usually is (e.g. Groq/Google return a JSON error message).
    Surface it so the .txt reports are self-diagnosing instead of just '403 Forbidden'."""
    if not resp.ok:
        raise requests.HTTPError(f"{resp.status_code} {resp.reason} — body: {resp.text[:500]}")


def call_openai(prompt: str, model_key: str = "gpt5") -> str:
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    return resp.json()["choices"][0]["message"]["content"]


def call_anthropic(prompt: str, model_key: str = "claude") -> str:
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model_id,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    blocks = resp.json()["content"]
    return "".join(b["text"] for b in blocks if b.get("type") == "text")


def call_google(prompt: str, model_key: str = "gemini") -> str:
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_groq(prompt: str, model_key: str) -> str:
    """
    Groq free tier: ~30 req/min, ~6,000 tokens/min, ~1,000 req/day per model.
    We pace calls with a minimum delay to stay under the per-minute caps and
    retry once on a 429 with the Retry-After header (falls back to a fixed wait).
    """
    global _last_groq_call
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]

    elapsed = time.time() - _last_groq_call
    if elapsed < GROQ_MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(GROQ_MIN_SECONDS_BETWEEN_CALLS - elapsed)

    for attempt in range(2):
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=LLM_TIMEOUT_SEC,
        )
        _last_groq_call = time.time()

        if resp.status_code == 429 and attempt == 0:
            wait = int(resp.headers.get("Retry-After", 20))
            time.sleep(wait)
            continue

        _raise_with_body(resp)
        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError(f"Groq rate-limited twice in a row for {model_key}")


def call_dashscope(prompt: str, model_key: str = "qwen") -> str:
    """Qwen via Alibaba DashScope (OpenAI-compatible endpoint)."""
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    resp = requests.post(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    return resp.json()["choices"][0]["message"]["content"]

def call_openrouter(prompt: str, model_key: str) -> str:
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    return resp.json()["choices"][0]["message"]["content"]


from config import LIARA_API_BASE

def call_liara(prompt: str, model_key: str) -> str:
    key = _get_key(model_key)
    model_id = MODELS[model_key]["model_id"]
    resp = requests.post(
        f"{LIARA_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model_id, "messages": [{"role": "user", "content": prompt}]},
        timeout=LLM_TIMEOUT_SEC,
    )
    _raise_with_body(resp)
    return resp.json()["choices"][0]["message"]["content"]

DISPATCH = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "google": call_google,
    "dashscope": call_dashscope,
    "groq": call_groq,
    "openrouter": call_openrouter,
    "liara": call_liara,
}


def call_llm(model_key: str, prompt: str) -> str:
    provider = MODELS[model_key]["provider"]
    return DISPATCH[provider](prompt, model_key)
