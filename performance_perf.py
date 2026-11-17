"""
Measures throughput, CPU usage, and peak (max RSS) memory for a compiled,
standalone Java program (i.e. one with public static void main).

Why not JMH: JMH benchmarks a single reusable method invoked many times in a
warmed-up loop. These generated programs are whole standalone concurrent
programs (fixed thread pools, main()-driven), so there's no uniform method
signature to plug into a JMH @Benchmark across 115 different programs without
writing a custom adapter per program. Instead we run the whole program
end-to-end, repeated N times, and use the OS (`/usr/bin/time -v`) to capture
wall-clock time, CPU%, and max RSS per run -- this works identically for
every program with zero per-program code.

Requires GNU time: `sudo apt-get install time` (the shell built-in `time`
does NOT support -v).
"""

import re
import statistics
import subprocess
from config import JAVA, GNU_TIME_CMD, PERF_TIMEOUT_SEC, PERF_REPETITIONS

_ELAPSED_RE = re.compile(r"Elapsed \(wall clock\) time.*?: (?:(\d+):)?(\d+):(\d+\.?\d*)")
_CPU_RE = re.compile(r"Percent of CPU this job got: (\d+)%")
_MAXRSS_RE = re.compile(r"Maximum resident set size \(kbytes\): (\d+)")


def _parse_elapsed(s: str) -> float:
    m = _ELAPSED_RE.search(s)
    if not m:
        return None
    h, mm, ss = m.groups()
    h = int(h) if h else 0
    return h * 3600 + int(mm) * 60 + float(ss)


def run_performance(class_name: str, workdir: str, reps: int = PERF_REPETITIONS):
    """
    Runs the program `reps` times, each timed/profiled independently.
    Returns a dict with throughput (runs/sec), avg/median CPU%, avg/peak max-RSS (KB),
    number of successful/failed/timed-out runs, and the raw per-run logs.
    """
    elapsed_times, cpu_pcts, max_rss = [], [], []
    failures, timeouts = 0, 0
    raw_logs = []

    for i in range(reps):
        cmd = [GNU_TIME_CMD, "-v", JAVA, "-cp", workdir, class_name]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=PERF_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            timeouts += 1
            continue

        log = proc.stderr  # GNU time -v writes its report to stderr
        raw_logs.append(f"--- run {i+1} (exit={proc.returncode}) ---\n{log}")

        if proc.returncode != 0:
            failures += 1
            # still try to harvest timing/memory stats even if the program itself errored
        et = _parse_elapsed(log)
        cpu_m = _CPU_RE.search(log)
        rss_m = _MAXRSS_RE.search(log)
        if et is not None:
            elapsed_times.append(et)
        if cpu_m:
            cpu_pcts.append(int(cpu_m.group(1)))
        if rss_m:
            max_rss.append(int(rss_m.group(1)))

    successful_runs = reps - failures - timeouts
    throughput = (successful_runs / sum(elapsed_times)) if elapsed_times and sum(elapsed_times) > 0 else None

    return {
        "reps_requested": reps,
        "successful_runs": successful_runs,
        "failures": failures,
        "timeouts": timeouts,
        "throughput_runs_per_sec": round(throughput, 4) if throughput else None,
        "avg_elapsed_sec": round(statistics.mean(elapsed_times), 4) if elapsed_times else None,
        "median_elapsed_sec": round(statistics.median(elapsed_times), 4) if elapsed_times else None,
        "avg_cpu_percent": round(statistics.mean(cpu_pcts), 1) if cpu_pcts else None,
        "avg_max_rss_kb": round(statistics.mean(max_rss), 1) if max_rss else None,
        "peak_max_rss_kb": max(max_rss) if max_rss else None,
        "raw_logs": "\n".join(raw_logs),
    }
