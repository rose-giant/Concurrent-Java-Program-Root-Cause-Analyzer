import os
import subprocess
from config import JAVAC, JPF_RUN_CMD, COMPILE_TIMEOUT_SEC, JPF_TIMEOUT_SEC

JPF_TEMPLATE = """target = {class_name}
classpath = {classpath}
listener = gov.nasa.jpf.listener.PreciseRaceDetector
search.multiple_errors = true
"""


def compile_java(code: str, class_name: str, workdir: str):
    """Write code to <class_name>.java and compile it. Returns (ok, log)."""
    os.makedirs(workdir, exist_ok=True)
    src_path = os.path.join(workdir, f"{class_name}.java")
    with open(src_path, "w") as f:
        f.write(code)

    try:
        proc = subprocess.run(
            [JAVAC, "-d", workdir, src_path],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, "COMPILE TIMEOUT"

    ok = proc.returncode == 0
    log = proc.stdout + proc.stderr
    return ok, log


def run_jpf(class_name: str, workdir: str):
    """
    Runs JPF against the compiled class looking for deadlocks / data races /
    uncaught exceptions / assertion violations.
    Returns (verdict, log) where verdict in {"NO_ERRORS_FOUND", "ERRORS_FOUND", "TIMEOUT", "JPF_FAILED"}.
    """
    jpf_conf_path = os.path.join(workdir, f"{class_name}.jpf")
    with open(jpf_conf_path, "w") as f:
        f.write(JPF_TEMPLATE.format(class_name=class_name, classpath=workdir))

    try:
        proc = subprocess.run(
            JPF_RUN_CMD + [jpf_conf_path],
            capture_output=True, text=True, timeout=JPF_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "JPF did not finish within timeout (possible non-terminating program or huge state space)"

    log = proc.stdout + proc.stderr

    if "no errors detected" in log.lower():
        return "NO_ERRORS_FOUND", log
    if "error" in log.lower() and "jpf" in log.lower():
        # distinguish JPF crashing/misconfigured vs. actually finding a defect
        if "gov.nasa.jpf" in log and ("exception" in log.lower() and "search finished" not in log.lower()):
            return "JPF_FAILED", log
        return "ERRORS_FOUND", log
    return "JPF_FAILED", log
