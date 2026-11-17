"""
Static concurrency analysis via SpotBugs. Runs entirely on the compiled
bytecode -- never executes the program -- so there's no JDK-version
compatibility risk the way there was with JPF's runtime bytecode modeling.

Detects structural concurrency antipatterns (SpotBugs' MT_CORRECTNESS
category): inconsistent synchronization, broken double-checked locking,
synchronizing on non-final fields, naked notify(), sleep-while-holding-lock,
etc. This is a heuristic bug-pattern matcher, not a sound/complete verifier
like a model checker -- it can have false positives and will miss defects
outside its known patterns. Treat findings as "worth a human look," not
proof of a defect.

Setup: download a SpotBugs release (https://github.com/spotbugs/spotbugs/releases),
unzip it, and set SPOTBUGS_HOME in config.py to the unzipped directory.
"""

import os
import re
import subprocess
from config import SPOTBUGS_CMD, SPOTBUGS_TIMEOUT_SEC

# SpotBugs' -textui short-format output looks like:
#   M M DC: Possible double-check on Foo.instance in Foo.getInstance()  At Foo.java:[lines 4-6]
# i.e. "<confidence> <priority> <SHORT_CODE>: <description>"
_FINDING_LINE_RE = re.compile(r"^[A-Z]\s[A-Z]\s([A-Z][A-Z0-9]*):\s")


def run_spotbugs(class_name: str, workdir: str):
    """
    Runs SpotBugs against the compiled classes in `workdir`, filtered to the
    MT_CORRECTNESS (concurrency) bug category at low confidence threshold
    (most inclusive -- surfaces more candidates for review).

    Returns (verdict, findings, raw_log) where:
      verdict  in {"NO_FINDINGS", "FINDINGS_PRESENT", "SPOTBUGS_FAILED", "TIMEOUT"}
      findings is a list of raw finding lines (bug pattern + location)
      raw_log  is the full stdout+stderr for manual inspection
    """
    try:
        proc = subprocess.run(
            SPOTBUGS_CMD + [
                "-textui",
                "-bugCategories", "MT_CORRECTNESS",
                "-low",
                "-effort:max",
                workdir,
            ],
            capture_output=True, text=True, timeout=SPOTBUGS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", [], "SpotBugs did not finish within timeout"
    except FileNotFoundError:
        return "SPOTBUGS_FAILED", [], (
            "SpotBugs executable not found -- check SPOTBUGS_HOME in config.py "
            "points at an unzipped SpotBugs release directory"
        )

    log = proc.stdout + proc.stderr

    if proc.returncode not in (0, 1):  # SpotBugs textui: 0 = clean, 1 = bugs found
        return "SPOTBUGS_FAILED", [], log

    findings = [line.strip() for line in proc.stdout.splitlines() if _FINDING_LINE_RE.match(line.strip())]

    if findings:
        return "FINDINGS_PRESENT", findings, log
    return "NO_FINDINGS", [], log
