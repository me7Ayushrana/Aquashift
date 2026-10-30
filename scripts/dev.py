#!/usr/bin/env python3
"""AquaShift Cross-Platform Development Runner.

Launches FastAPI backend and Vite frontend development servers concurrently.
Handles graceful shutdown of all spawned child processes.
"""
import os
import sys
import subprocess
import signal
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def get_venv_python() -> str:
    """Locate the Python executable within the local virtual environment."""
    if sys.platform == "win32":
        venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = ROOT_DIR / ".venv" / "bin" / "python"

    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def main():
    python_bin = get_venv_python()
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    print("=" * 60)
    print("🌾 Starting AquaShift Development Environment")
    print(f"📁 Root directory: {ROOT_DIR}")
    print(f"🐍 Python executable: {python_bin}")
    print("=" * 60)

    processes = []

    # Backend environment
    backend_env = os.environ.copy()
    backend_env["PYTHONPATH"] = str(ROOT_DIR)

    try:
        # Start Backend Server
        print("🚀 Starting FastAPI backend on http://localhost:8000 ...")
        backend_proc = subprocess.Popen(
            [python_bin, "-m", "uvicorn", "backend.app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(ROOT_DIR),
            env=backend_env,
        )
        processes.append(backend_proc)

        # Start Frontend Server
        print("✨ Starting Vite frontend on http://localhost:5173 ...")
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=str(FRONTEND_DIR),
        )
        processes.append(frontend_proc)

        print("\n✅ AquaShift servers running. Press Ctrl+C to terminate.\n")

        while True:
            for p in processes:
                ret = p.poll()
                if ret is not None:
                    print(f"⚠️ Process {p.args} exited with code {ret}")
                    return ret
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down AquaShift servers...")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("👋 AquaShift dev processes cleanly terminated.")


if __name__ == "__main__":
    sys.exit(main() or 0)
