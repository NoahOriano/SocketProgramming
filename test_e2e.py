"""Simple end-to-end test harness for Program A and Program B.

This script:

1. Starts Program B (UDP server + TCP client) as a background subprocess.
2. Waits briefly for B to start listening.
3. Starts Program A (TCP server + UDP client) as a foreground subprocess.
4. Captures Program A's stdout and checks that it printed a single
   integer (the computed sum).
5. Terminates Program B.

Usage:

    python test_e2e.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_e2e() -> int:
    """Run Program B then Program A and check A's output.

    Returns process exit code (0 for success, non-zero for failure).
    """

    # Start Program B
    print("[TEST] Starting Program B...", flush=True)
    proc_b = subprocess.Popen(
        [sys.executable, "program_b.py", "--a-host", "127.0.0.1", "--udp-port", "5000", "--tcp-port", "5001"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give B a moment to start listening
        time.sleep(1.0)

        print("[TEST] Starting Program A...", flush=True)
        proc_a = subprocess.Popen(
            [sys.executable, "program_a.py", "--b-host", "127.0.0.1", "--udp-port", "5000", "--tcp-port", "5001"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout_a, stderr_a = proc_a.communicate(timeout=10.0)

        print("[TEST] Program A stdout:\n" + stdout_a)
        print("[TEST] Program A stderr:\n" + stderr_a)

        if proc_a.returncode != 0:
            print(f"[TEST] Program A exited with non-zero code {proc_a.returncode}")
            return 1

        # Expect at least one line with an integer
        lines = [line.strip() for line in stdout_a.splitlines() if line.strip()]
        if not lines:
            print("[TEST] No output from Program A")
            return 1

        last_line = lines[-1]
        try:
            value = int(last_line)
        except ValueError:
            print(f"[TEST] Last line from Program A is not an integer: {last_line!r}")
            return 1

        print(f"[TEST] Parsed integer from Program A: {value}")
        # Basic sanity: value should be positive and within uint32 range
        if not (0 < value <= 0xFFFFFFFF):
            print("[TEST] Parsed value is out of expected range")
            return 1

        print("[TEST] End-to-end test PASSED")
        return 0

    except subprocess.TimeoutExpired:
        print("[TEST] Program A timed out")
        proc_a.kill()
        return 1
    finally:
        # Try to cleanly terminate Program B
        proc_b.terminate()
        try:
            proc_b.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc_b.kill()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_e2e())
