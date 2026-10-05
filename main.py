"""
EcoTravel Advisor – Main Unified Orchestrator & Launcher

Run this file with:
    python main.py
or
    .venv\\Scripts\\python.exe main.py

This script automatically:
  1. Checks virtual environment & credentials loaded status
  2. Starts the Rasa Action Server on port 5055
  3. Waits for the Action Server health check to pass
  4. Starts the Rasa Core/NLU API Server on port 5005
  5. Waits for the Rasa API Server status check to pass
  6. Starts the Web Frontend HTTP Server on port 8080
  7. Automatically opens http://localhost:8080 in your default web browser
  8. Gracefully manages all background processes and cleans them up on Ctrl+C
"""

import sys
import os
import time
import subprocess
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output encoding for Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Select Python & Rasa executables (prefer virtual environment)
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
VENV_RASA = BASE_DIR / ".venv" / "Scripts" / "rasa.exe"

PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
RASA_EXE = str(VENV_RASA) if VENV_RASA.exists() else "rasa"

processes = []

def print_banner():
    print("=" * 65)
    print("       EcoTravel Advisor -- Orchestrated System Launcher       ")
    print("=" * 65)

def check_credentials():
    load_dotenv(BASE_DIR / ".env")
    print("\n[1/5] Checking Environment & Credentials...")
    climatiq = bool(os.getenv("CLIMATIQ_API_KEY"))
    amadeus_key = bool(os.getenv("AMADEUS_API_KEY"))
    amadeus_secret = bool(os.getenv("AMADEUS_API_SECRET"))
    
    print(f"  * CLIMATIQ_API_KEY loaded: {climatiq}")
    print(f"  * AMADEUS_API_KEY loaded: {amadeus_key}")
    print(f"  * AMADEUS_API_SECRET loaded: {amadeus_secret}")

def wait_for_url(url, description, timeout=120):
    print(f"  * Waiting for {description} at {url} ...", end="", flush=True)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EcoTravelLauncher/1.0"})
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

def start_action_server():
    print("\n[2/5] Starting Rasa Action Server (Port 5055)...")
    cmd = [PYTHON_EXE, "-m", "rasa_sdk", "--actions", "actions"]
    p = subprocess.Popen(cmd, cwd=BASE_DIR)
    processes.append(("Action Server", p))
    wait_for_url("http://localhost:5055/health", "Action Server")

def start_rasa_server():
    print("\n[3/5] Starting Rasa API Server (Port 5005)...")
    cmd = [RASA_EXE, "run", "--enable-api", "--cors", "*"]
    p = subprocess.Popen(cmd, cwd=BASE_DIR)
    processes.append(("Rasa API Server", p))
    wait_for_url("http://localhost:5005/status", "Rasa API Server")

def start_frontend_server():
    print("\n[4/5] Starting Frontend HTTP Server (Port 8080)...")
    cmd = [PYTHON_EXE, "-m", "http.server", "8080", "--directory", "frontend"]
    p = subprocess.Popen(cmd, cwd=BASE_DIR)
    processes.append(("Frontend HTTP Server", p))
    wait_for_url("http://localhost:8080", "Frontend HTTP Server")

def open_browser():
    print("\n[5/5] Opening Frontend in Web Browser...")
    url = "http://localhost:8080"
    print(f"  Web Interface URL: {url}")
    time.sleep(1)
    webbrowser.open(url)

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

def main():
    print_banner()
    check_credentials()
    
    try:
        start_action_server()
        start_rasa_server()
        start_frontend_server()
        open_browser()
        
        print("\n" + "=" * 65)
        print("ECOTRAVEL ADVISOR SERVICES ARE LIVE & RUNNING!")
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
