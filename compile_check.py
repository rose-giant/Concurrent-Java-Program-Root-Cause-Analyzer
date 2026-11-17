import os
import subprocess
from config import JAVAC, COMPILE_TIMEOUT_SEC


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
