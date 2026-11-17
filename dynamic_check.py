"""
Dynamic correctness checks that run the compiled program on a real,
unmodified JVM -- no bytecode re-modeling, so no JPF-style JDK-version
conflicts. Three checks, each cheap and standard-tooling-only:

1. Deadlock detection: if a run hangs past a timeout, take a thread dump
   with jstack *before* killing the process. The JVM itself reports
   "Found one Java-level deadlock" when one exists -- this is a completely
   reliable, zero-false-positive signal when it fires (unlike a hang, which
   could also just mean slow/looping code with no actual deadlock).
2. Uncaught exception detection: scan stderr across repeated runs for
   "Exception in thread" -- an uncaught exception escaping main() is always
   a real defect worth flagging regardless of concurrency semantics.
3. Output consistency: flag when repeated runs of the same program produce
   different stdout, which can indicate a real race (though it can also be
   expected nondeterminism, e.g. thread interleaving text order -- reported
   as a flag for review, not a definitive verdict).
"""

import os
import subprocess
import time
from config import JAVA, JSTACK, DYNAMIC_CHECK_REPS, DYNAMIC_CHECK_TIMEOUT_SEC


def _run_once_with_deadlock_watch(class_name: str, workdir: str, timeout: float):
    """Launches the program; if it hangs past `timeout`, takes a jstack dump
    before terminating it. Returns a dict describing this single run."""
    proc = subprocess.Popen(
        [JAVA, "-cp", workdir, class_name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    start = time.time()
    deadlock_log = None
    timed_out = False

    while True:
        ret = proc.poll()
        if ret is not None:
            break
        if time.time() - start > timeout:
            timed_out = True
            try:
                dump = subprocess.run(
                    [JSTACK, str(proc.pid)], capture_output=True, text=True, timeout=15,
                )
                deadlock_log = dump.stdout + dump.stderr
            except Exception as e:
                deadlock_log = f"(jstack failed: {e})"
            proc.kill()
            break
        time.sleep(0.2)

    stdout, stderr = proc.communicate(timeout=5) if proc.poll() is not None else ("", "")

    deadlock_found = bool(deadlock_log and "Found one Java-level deadlock" in deadlock_log)

    return {
        "timed_out": timed_out,
        "deadlock_found": deadlock_found,
        "deadlock_log": deadlock_log,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "uncaught_exception": "Exception in thread" in (stderr or ""),
    }


def run_dynamic_checks(class_name: str, workdir: str, reps: int = DYNAMIC_CHECK_REPS):
    """
    Runs the program `reps` times watching for deadlocks, uncaught exceptions,
    and output inconsistency. Returns a summary dict.
    """
    runs = [
        _run_once_with_deadlock_watch(class_name, workdir, DYNAMIC_CHECK_TIMEOUT_SEC)
        for _ in range(reps)
    ]

    deadlock_runs = [r for r in runs if r["deadlock_found"]]
    exception_runs = [r for r in runs if r["uncaught_exception"]]
    hang_no_deadlock_runs = [r for r in runs if r["timed_out"] and not r["deadlock_found"]]
    # A nonzero exit with no timeout, no deadlock, and no "Exception in thread"
    # text usually means the JVM itself failed to launch the class (e.g. class
    # not found, malformed classfile) -- distinct from a real program defect.
    launch_failure_runs = [
        r for r in runs
        if not r["timed_out"] and not r["deadlock_found"] and not r["uncaught_exception"]
        and r["exit_code"] not in (0, None)
    ]

    distinct_outputs = {r["stdout"] for r in runs if not r["timed_out"]}
    inconsistent_output = len(distinct_outputs) > 1

    if deadlock_runs:
        verdict = "DEADLOCK_DETECTED"
    elif exception_runs:
        verdict = "UNCAUGHT_EXCEPTION"
    elif hang_no_deadlock_runs:
        verdict = "HANG_NO_DEADLOCK_CONFIRMED"  # timed out but jstack didn't confirm deadlock -- could be slow/looping code
    elif launch_failure_runs:
        verdict = "LAUNCH_FAILURE"  # JVM couldn't even start the class -- check classpath/class name, not a concurrency defect
    elif inconsistent_output:
        verdict = "INCONSISTENT_OUTPUT"
    else:
        verdict = "CLEAN"

    return {
        "verdict": verdict,
        "reps": reps,
        "deadlock_runs": len(deadlock_runs),
        "exception_runs": len(exception_runs),
        "hang_no_deadlock_runs": len(hang_no_deadlock_runs),
        "launch_failure_runs": len(launch_failure_runs),
        "inconsistent_output": inconsistent_output,
        "distinct_output_count": len(distinct_outputs),
        "sample_deadlock_log": deadlock_runs[0]["deadlock_log"] if deadlock_runs else None,
        "sample_exception_stderr": exception_runs[0]["stderr"] if exception_runs else None,
        "sample_launch_failure_stderr": launch_failure_runs[0]["stderr"] if launch_failure_runs else None,
    }
