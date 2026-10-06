"""
EcoTravel Advisor – Main Unified Orchestrator & Launcher

Run this file with:
    python main.py
or
    .venv\\Scripts\\python.exe main.py

This script automatically:
  1. Locates a compatible Python (3.10.x) required by Rasa 3.6
  2. Validates the virtual environment (detects stale / broken venvs)
  3. Recreates the venv and installs dependencies if needed
  4. Checks API credentials from .env
  5. Starts the Rasa Action Server on port 5055
  6. Waits for the Action Server health check to pass
  7. Starts the Rasa Core/NLU API Server on port 5005
  8. Waits for the Rasa API Server status check to pass
  9. Starts the Web Frontend HTTP Server on port 8080
  10. Automatically opens http://localhost:8080 in your default web browser
  11. Gracefully manages all background processes and cleans them up on Ctrl+C
"""

import sys
import os
import time
import subprocess
import urllib.request
import urllib.error
import webbrowser
import shutil
import glob
from pathlib import Path

# Ensure UTF-8 output encoding for Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── CONSTANTS ────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"
VENV_RASA = VENV_DIR / "Scripts" / "rasa.exe"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"

# Rasa 3.6 requires Python >=3.8,<3.11 — so we need 3.10.x
REQUIRED_PYTHON_MAJOR = 3
REQUIRED_PYTHON_MINOR = 10

processes = []


# ── BANNER ───────────────────────────────────────────────────
def print_banner():
    print("=" * 65)
    print("       EcoTravel Advisor -- Orchestrated System Launcher       ")
    print("=" * 65)


def print_step(step, total, msg):
    print(f"\n[{step}/{total}] {msg}")


# ── FIND COMPATIBLE PYTHON ───────────────────────────────────
def find_compatible_python():
    """
    Locate a Python 3.10.x interpreter on this machine.
    Search order:
      1. Common Windows install paths (AppData, C:\\PythonXX)
      2. PATH-based discovery via `where python` / `py -3.10`
    Returns the absolute path string, or None if not found.
    """
    candidates = []

    # 1. Check common install locations
    user_home = Path.home()
    search_dirs = [
        user_home / "AppData" / "Local" / "Programs" / "Python" / "Python310",
        Path("C:/Python310"),
        Path("C:/Python/Python310"),
        Path("C:/Program Files/Python310"),
        Path("C:/Program Files (x86)/Python310"),
    ]
    for d in search_dirs:
        exe = d / "python.exe"
        if exe.exists():
            candidates.append(str(exe))

    # 2. Try the `py` launcher (Windows Python Launcher)
    try:
        result = subprocess.run(
            ["py", f"-{REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR}", "-c",
             "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path and Path(path).exists():
                candidates.append(path)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 3. Check PATH for python3.10 or python executables
    try:
        result = subprocess.run(
            ["where", "python"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line and Path(line).exists():
                    candidates.append(line)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Validate candidates — check version
    for exe_path in candidates:
        try:
            result = subprocess.run(
                [exe_path, "-c",
                 "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                if version == f"{REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR}":
                    return exe_path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue

    return None


# ── VENV VALIDATION ──────────────────────────────────────────
def is_venv_healthy():
    """
    Check that the virtual environment exists and its Python actually works.
    A venv created on a different machine will have broken shebang paths.
    """
    if not VENV_PYTHON.exists():
        return False, "python.exe not found in .venv"

    # Try running the venv Python
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", "import sys; print(sys.version)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False, f"venv Python failed: {result.stderr.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return False, f"venv Python error: {e}"

    # Check that key packages are importable
    for pkg in ["rasa", "rasa_sdk", "dotenv"]:
        try:
            result = subprocess.run(
                [str(VENV_PYTHON), "-c", f"import {pkg}"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                return False, f"package '{pkg}' not importable"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False, f"failed to check package '{pkg}'"

    # Check rasa executable
    if not VENV_RASA.exists():
        return False, "rasa.exe not found in .venv"

    return True, "OK"


# ── VENV CREATION ────────────────────────────────────────────
def setup_virtual_environment(python_exe):
    """
    Delete the broken venv (if any) and create a fresh one using
    the provided compatible Python executable. Install all requirements.
    """
    # Remove broken venv
    if VENV_DIR.exists():
        print("  * Removing broken/stale virtual environment...")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        # In case rmtree fails on some locked files, wait and retry
        if VENV_DIR.exists():
            time.sleep(2)
            shutil.rmtree(VENV_DIR, ignore_errors=True)

    # Create fresh venv
    print(f"  * Creating virtual environment with: {python_exe}")
    result = subprocess.run(
        [python_exe, "-m", "venv", str(VENV_DIR)],
        cwd=str(BASE_DIR), timeout=120
    )
    if result.returncode != 0:
        print("  [ERROR] Failed to create virtual environment.")
        sys.exit(1)

    # Upgrade pip
    print("  * Upgrading pip...")
    subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=str(BASE_DIR), timeout=120,
        stdout=subprocess.DEVNULL
    )

    # Install requirements
    if REQUIREMENTS_FILE.exists():
        print(f"  * Installing dependencies from requirements.txt...")
        print("    (This may take several minutes for Rasa — please be patient)")
        result = subprocess.run(
            [str(VENV_PIP), "install", "-r", str(REQUIREMENTS_FILE)],
            cwd=str(BASE_DIR), timeout=900
        )
        if result.returncode != 0:
            print("  [ERROR] pip install failed. Check the output above for details.")
            sys.exit(1)
    else:
        print(f"  [WARNING] {REQUIREMENTS_FILE} not found — skipping dependency install.")

    print("  [DONE] Virtual environment ready.")


# ── ENVIRONMENT SETUP (STEP 1) ───────────────────────────────
def ensure_environment():
    """
    Master setup function. Validates venv; if broken, finds compatible
    Python and rebuilds everything automatically.
    """
    print_step(1, 7, "Checking Virtual Environment...")

    healthy, reason = is_venv_healthy()

    if healthy:
        print(f"  * Virtual environment OK ✓")
        return

    print(f"  * Virtual environment issue detected: {reason}")
    print(f"  * Searching for Python {REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR} on this system...")

    python_exe = find_compatible_python()

    if not python_exe:
        print()
        print("=" * 65)
        print(f"  ERROR: Python {REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR} is required but not found.")
        print()
        print("  Rasa 3.6 requires Python 3.10.x to run correctly.")
        print("  Please install Python 3.10 from: https://www.python.org/downloads/")
        print("  Then re-run this script.")
        print("=" * 65)
        sys.exit(1)

    print(f"  * Found compatible Python: {python_exe}")
    setup_virtual_environment(python_exe)


# ── CREDENTIALS CHECK (STEP 2) ──────────────────────────────
def check_credentials():
    # Load dotenv using the venv's python to ensure compatibility
    # But also try locally for display purposes
    try:
        from dotenv import load_dotenv as _ld
        _ld(BASE_DIR / ".env")
    except ImportError:
        # If dotenv not available in the outer Python, load .env manually
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    print_step(2, 7, "Checking API Credentials...")
    climatiq = bool(os.getenv("CLIMATIQ_API_KEY"))
    amadeus_key = bool(os.getenv("AMADEUS_API_KEY"))
    amadeus_secret = bool(os.getenv("AMADEUS_API_SECRET"))

    print(f"  * CLIMATIQ_API_KEY loaded: {climatiq}")
    print(f"  * AMADEUS_API_KEY loaded: {amadeus_key}")
    print(f"  * AMADEUS_API_SECRET loaded: {amadeus_secret}")

    if not all([climatiq, amadeus_key, amadeus_secret]):
        print("  [WARNING] Some API keys are missing — certain features may not work.")
        print(f"            Check your .env file at: {BASE_DIR / '.env'}")


# ── PORT FREER ───────────────────────────────────────────────
def free_port(port):
    """
    Check if a port is in use and terminate any process listening on it.
    Prevents 'OSError: [Errno 10048] address already in use' errors.
    """
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                f"netstat -ano | findstr :{port}", shell=True, text=True, errors="ignore"
            )
            pids = set()
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                        pids.add(int(pid))
            for pid in pids:
                try:
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"  * Cleared stale process on port {port} (PID {pid})")
                except Exception:
                    pass
        except Exception:
            pass
    else:
        try:
            output = subprocess.check_output(["lsof", "-t", f"-i:{port}"], text=True, errors="ignore")
            for pid_str in output.splitlines():
                if pid_str.strip().isdigit():
                    pid = int(pid_str.strip())
                    if pid != os.getpid():
                        os.kill(pid, 9)
                        print(f"  * Cleared stale process on port {port} (PID {pid})")
        except Exception:
            pass


# ── HEALTH CHECK ─────────────────────────────────────────────
def wait_for_url(url, description, timeout=120):
    urls_to_try = [url]
    if "localhost" in url:
        urls_to_try.append(url.replace("localhost", "127.0.0.1"))

    print(f"  * Waiting for {description} at {url} ...", end="", flush=True)
    start_time = time.time()
    while time.time() - start_time < timeout:
        for target_url in urls_to_try:
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "EcoTravelLauncher/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status in (200, 204):
                        print(" [READY]")
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError, Exception):
                pass
        time.sleep(2)
        print(".", end="", flush=True)
    print(" [Timeout reached]")
    return False


# ── SERVICE LAUNCHERS ────────────────────────────────────────
def start_action_server():
    print_step(3, 7, "Starting Rasa Action Server (Port 5055)...")
    free_port(5055)
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    cmd = [str(VENV_PYTHON), "-W", "ignore", "-m", "rasa_sdk", "--actions", "actions"]
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
    processes.append(("Action Server", p))
    if not wait_for_url("http://localhost:5055/health", "Action Server"):
        print("  [WARNING] Action Server may not be ready — continuing anyway.")


def start_rasa_server():
    print_step(4, 7, "Starting Rasa API Server (Port 5005)...")
    free_port(5005)
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    cmd = [str(VENV_PYTHON), "-W", "ignore", "-m", "rasa", "run", "--enable-api", "--cors", "*"]
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
    processes.append(("Rasa API Server", p))
    if not wait_for_url("http://localhost:5005/status", "Rasa API Server", timeout=300):
        print("  [WARNING] Rasa Server may not be ready — continuing anyway.")


def start_frontend_server():
    print_step(5, 7, "Starting Frontend HTTP Server (Port 8080)...")
    free_port(8080)
    cmd = [sys.executable, "-m", "http.server", "8080", "--directory", "frontend"]
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR))
    processes.append(("Frontend HTTP Server", p))
    if not wait_for_url("http://localhost:8080", "Frontend HTTP Server", timeout=15):
        print("  [WARNING] Frontend Server may not be ready — continuing anyway.")


def open_browser():
    print_step(6, 7, "Opening Frontend in Web Browser...")
    url = "http://localhost:8080"
    print(f"  * Web Interface URL: {url}")
    time.sleep(1)
    webbrowser.open(url)


# ── CLEANUP ──────────────────────────────────────────────────
def cleanup():
    print("\n" + "=" * 65)
    print("  Stopping EcoTravel Advisor servers...")
    print("=" * 65)
    for name, p in reversed(processes):
        if p.poll() is None:
            print(f"  * Stopping {name} (PID {p.pid})...")
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    print("  [Done] All services stopped safely.")


# ── MAIN ─────────────────────────────────────────────────────
def main():
    print_banner()

    # Step 1: Ensure venv is valid (auto-repair if needed)
    ensure_environment()

    # Step 2: Check API credentials
    check_credentials()

    try:
        # Steps 3-6: Launch services
        start_action_server()
        start_rasa_server()
        start_frontend_server()
        open_browser()

        # Step 7: Running
        print_step(7, 7, "All Systems Live!")
        print("=" * 65)
        print("  ECOTRAVEL ADVISOR SERVICES ARE LIVE & RUNNING!")
        print("  * Web Interface:    http://localhost:8080")
        print("  * Rasa API Server:  http://localhost:5005")
        print("  * Action Server:    http://localhost:5055")
        print("=" * 65)
        print("Press Ctrl+C at any time to stop all servers gracefully.\n")

        warned = set()
        while True:
            time.sleep(1)
            # Check if any process terminated unexpectedly
            for name, p in processes:
                if p.poll() is not None and name not in warned:
                    print(f"\n* Warning: {name} exited with code {p.returncode}.")
                    warned.add(name)

    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"\n* Error encountered: {e}")
        cleanup()


if __name__ == "__main__":
    main()
