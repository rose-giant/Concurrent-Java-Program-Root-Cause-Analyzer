# Concurrency Benchmark Pipeline

Automates: `prompts.csv` → 4 LLMs → generated Java → compile → JPF (concurrency
correctness) → repeated execution (throughput / CPU / memory) → one `.txt`
report per (prompt, LLM) in `results/`.

## 1. Install prerequisites

- **JDK 8** (the prompts target Java 8) — `javac`/`java` on PATH, or set
  `JDK_BIN` in `config.py`.
- **Java PathFinder (JPF)** — build `jpf-core`, and make sure `~/.jpf/site.properties`
  points to it. Either put the `jpf` launcher script on PATH, or set
  `JPF_RUN_CMD` in `config.py` to
  `["java", "-jar", "/path/to/jpf-core/build/RunJPF.jar"]`.
- **GNU time** (for CPU%/memory measurement): `sudo apt-get install time`
  (the shell built-in `time` does *not* support `-v` — you need the real binary
  at `/usr/bin/time`).
- **Python 3.9+** and `pip install requests`.

## 2. Set API keys

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GOOGLE_API_KEY=...
export DASHSCOPE_API_KEY=...   # Qwen, via Alibaba DashScope
```

Check `config.py` → `MODELS` for exact model IDs; update them if a name has
changed (e.g. `gpt-5`, `claude-sonnet-4-6`, `gemini-2.5-pro`, `qwen-max`).

## 3. Run

```bash
cd pipeline
python3 orchestrator.py
```

This processes all 115 rows × 4 models = 460 runs. It prints progress and
writes one report to `results/<topic-slug>__<model>.txt` per run.

## 4. What each report contains

- Compilation status (+log if it failed)
- JPF verdict:
  - `NO_ERRORS_FOUND` — no deadlock / data race / uncaught exception found
    within JPF's search bounds
  - `ERRORS_FOUND` — JPF found a concurrency defect (see raw log at bottom
    of the report for the trace)
  - `TIMEOUT` — search didn't finish (common if the generated code has a
    real busy/infinite loop — see note below)
  - `JPF_FAILED` — JPF itself errored (bad classpath, unsupported bytecode, etc.)
- Performance: throughput (successful full-program runs/sec across 20
  repetitions by default), average/median wall-clock time, average CPU%,
  average and peak max-RSS memory (KB)
- The full generated code
- Raw JPF log, for manual inspection of any detected defect

## 5. Why not JMH?

JMH benchmarks one reusable `@Benchmark`-annotated method invoked repeatedly
after JIT warm-up. Your 115 generated programs are standalone
`public static void main` programs with varying structure (fixed thread
pools, `while` loops gated on a volatile flag, `CountDownLatch`, etc.) — there's
no single method signature you could plug into JMH across all of them without
hand-writing a custom adapter *per program*, which reintroduces the manual
work you're trying to eliminate.

Instead, `performance_perf.py` runs each whole program end-to-end N times
(default 20, configurable in `config.py`) using `/usr/bin/time -v`, which
gives wall-clock time, CPU%, and max RSS uniformly for every program with
zero per-program code. Throughput here means "full program completions per
second" — a reasonable proxy given these are short-lived concurrent programs,
not long-running services.

If you'd rather have finer-grained CPU/GC/heap sampling *during* execution
(not just peak/aggregate), swap in JDK Flight Recorder instead:
```bash
java -XX:+FlightRecorder -XX:StartFlightRecording=filename=rec.jfr,settings=profile -cp <dir> <Class>
jfr print --events jdk.CPULoad,jdk.GCHeapSummary rec.jfr
```
This is more detailed but requires parsing the JFR text output; I kept the
default implementation on `/usr/bin/time -v` because it's a single regex and
works identically across all 115 programs. Happy to swap in a JFR-based
`performance_jfr.py` instead if you want that level of detail.

## 6. Known limitations / things to sanity-check on real runs

- **Programs with genuine infinite loops** (a few of these prompts describe
  busy-wait patterns) will hit `PERF_TIMEOUT_SEC` during performance runs and
  `JPF_TIMEOUT_SEC` during JPF — both are configurable in `config.py`. You may
  want to eyeball the topic list and shorten timeouts for known-short programs
  vs. lengthening them for anything with real work inside the loop.
- **JPF only checks concurrency properties** (deadlock, data race, uncaught
  exception/assertion), not whether the program is functionally "correct" per
  the prompt's English description — that's inherent to what JPF verifies,
  not a gap in the pipeline. If you also want functional-behavior checking
  you'd need per-prompt test oracles, which isn't practical to automate given
  each prompt describes different behavior.
- **Model IDs will drift.** Double check `config.py` → `MODELS` against each
  provider's current docs before a big run — a stale model ID just fails
  cleanly (reported as `PIPELINE ERROR` in the .txt), so it's safe either way.
- The extractor assumes the response is a single ```` ```java ``` ```` fenced
  block, which matches your prompts' instruction ("Output a single complete
  code block using java. Do not include any explanations"). If a model still
  wraps it in the prose, `extract_java_code` falls back to using the whole
  response — check a couple of reports after the first run to confirm this
  isn't happening silently.

## 7. Files

```
config.py              -- edit paths / models / timeouts here
llm_clients.py          -- API wrappers for GPT-5, Claude, Gemini, Qwen
code_extractor.py       -- pulls Java code + class name out of LLM response
correctness_jpf.py      -- compiles code, runs JPF, parses verdict
performance_perf.py     -- runs program N times via `time -v`, aggregates stats
orchestrator.py         -- main entry point, ties it all together
prompts.csv             -- your 115 benchmark prompts
results/                -- output .txt reports (created on first run)
work/                   -- scratch dir for compiled .class files (created on first run)
```
