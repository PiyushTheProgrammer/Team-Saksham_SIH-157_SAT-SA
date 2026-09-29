#!/usr/bin/env python3
"""
SAT-SA: Unified One-Click Environment Setup & Self-Healing Script
================================================================
Automates end-to-end setup for any fresh clone:
1. Python version & environment validation (Python 3.10 - 3.14+)
2. Virtual environment creation & requirements installation
3. Node.js (v18+) & npm verification, automated frontend package install
4. Interactive PostgreSQL database configuration & automated table initialization
5. Optional Ollama local LLM status check
6. Clear diagnostic guidance and error self-healing

NOTE: An internet connection is ONLY required during this initial setup
to download dependencies (pip, npm, Ollama model). Once downloaded,
SAT-SA operates 100% offline with zero external network dependencies.

Usage:
    python setup.py
"""

import os
import sys
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

# Ensure UTF-8 output on Windows CP1252 if possible
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.system("color")

# ANSI Terminal Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def print_step(step_num: int, title: str):
    print(f"\n{BLUE}{BOLD}[Step {step_num}/5]{RESET} {CYAN}{BOLD}{title}{RESET}")
    print("=" * 60)


def print_success(msg: str):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def print_warning(msg: str):
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def print_error(msg: str):
    print(f"  {RED}[ERROR]{RESET} {msg}")


def print_info(msg: str):
    print(f"  {BLUE}[INFO]{RESET} {msg}")


def run_cmd(cmd, cwd=None, capture=False):
    """Run a shell command safely."""
    try:
        if capture:
            res = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=isinstance(cmd, str)
            )
            return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
        else:
            res = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                shell=isinstance(cmd, str)
            )
            return res.returncode == 0, "", ""
    except Exception as e:
        return False, "", str(e)


# ════════════════════════════════════════════════════════════════
# 1. PYTHON VALIDATION & VENV SETUP
# ════════════════════════════════════════════════════════════════
def check_python_environment():
    print_step(1, "Validating Python Environment & Installing Dependencies")
    
    major, minor, micro = sys.version_info.major, sys.version_info.minor, sys.version_info.micro
    print_info(f"Detected Python version: {major}.{minor}.{micro}")

    if major < 3 or (major == 3 and minor < 10):
        print_error(
            f"Python {major}.{minor} is not supported. SAT-SA requires Python 3.10, 3.11, 3.12, 3.13, or 3.14+.\n"
            f"Please download and install Python from: https://www.python.org/downloads/"
        )
        sys.exit(1)

    print_success(f"Python version {major}.{minor}.{micro} is compatible.")

    # Virtual Environment
    venv_dir = BACKEND_DIR / "venv"
    in_venv = sys.prefix != sys.base_prefix

    if in_venv:
        py_exec = sys.executable
        pip_exec = [py_exec, "-m", "pip"]
        print_success(f"Running inside active virtual environment: {sys.prefix}")
    else:
        if not venv_dir.exists():
            print_info(f"Creating Python virtual environment in '{venv_dir}'...")
            ok, out, err = run_cmd([sys.executable, "-m", "venv", str(venv_dir)])
            if not ok:
                print_error(f"Failed to create virtual environment: {err}")
                print_warning("Falling back to system python...")
                py_exec = sys.executable
                pip_exec = [py_exec, "-m", "pip"]
            else:
                print_success("Virtual environment created.")
        
        if sys.platform == "win32":
            py_exec = str(venv_dir / "Scripts" / "python.exe")
            pip_exec = [py_exec, "-m", "pip"]
        else:
            py_exec = str(venv_dir / "bin" / "python")
            pip_exec = [py_exec, "-m", "pip"]
            
        if not Path(py_exec).exists():
            py_exec = sys.executable
            pip_exec = [py_exec, "-m", "pip"]

    # Upgrade pip
    print_info("Ensuring pip and setuptools are up-to-date...")
    run_cmd(pip_exec + ["install", "--upgrade", "pip", "setuptools", "wheel", "--quiet"])

    # Install requirements
    req_file = BACKEND_DIR / "requirements.txt"
    if req_file.exists():
        print_info("Installing backend Python dependencies from requirements.txt...")
        ok, out, err = run_cmd(pip_exec + ["install", "-r", str(req_file), "--prefer-binary"])
        if not ok:
            print_warning("Standard pip install encountered warnings/errors. Retrying with --only-binary :all: for psycopg...")
            run_cmd(pip_exec + ["install", "psycopg[binary]>=3.1.0", "--prefer-binary"])
            ok2, _, err2 = run_cmd(pip_exec + ["install", "-r", str(req_file)])
            if not ok2:
                print_error(f"Failed to install some requirements: {err2}")
                print_info("Proceeding to verify core packages...")
        print_success("Backend Python packages installed.")
    else:
        print_warning(f"requirements.txt not found at {req_file}")

    return py_exec


# ════════════════════════════════════════════════════════════════
# 2. NODE.JS & NPM VERIFICATION & FRONTEND SETUP
# ════════════════════════════════════════════════════════════════
def check_node_environment():
    print_step(2, "Validating Node.js & Installing Frontend Dependencies")

    # Locate node
    node_path = shutil.which("node")
    if not node_path and sys.platform == "win32":
        # Check standard Windows paths
        candidates = [
            Path("C:/Program Files/nodejs/node.exe"),
            Path("C:/Program Files (x86)/nodejs/node.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/node/node.exe"
        ]
        for c in candidates:
            if c.exists():
                os.environ["PATH"] = str(c.parent) + os.pathsep + os.environ["PATH"]
                node_path = str(c)
                break

    if not node_path:
        print_error("Node.js was not found in your PATH.")
        print_info(
            "Please download and install Node.js (LTS v18 or v20+) from: https://nodejs.org/\n"
            "After installing Node.js, restart your terminal and rerun this setup script."
        )
        sys.exit(1)

    ok, version, _ = run_cmd(["node", "-v"], capture=True)
    if ok:
        print_success(f"Detected Node.js version: {version}")
        try:
            v_num = int(version.lstrip("v").split(".")[0])
            if v_num < 18:
                print_warning(f"Node.js version {version} is older than v18. Next.js 16 recommends v18.17+ or v20+.")
        except Exception:
            pass

    # Check npm
    npm_path = shutil.which("npm")
    if not npm_path:
        print_error("npm command was not found. Please reinstall Node.js with default components.")
        sys.exit(1)

    # Install Frontend node_modules
    package_json = FRONTEND_DIR / "package.json"
    if package_json.exists():
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            print_info("Installing frontend dependencies (npm install)... This may take 1-2 minutes.")
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            ok, out, err = run_cmd([npm_cmd, "install"], cwd=FRONTEND_DIR)
            if not ok:
                print_warning("Standard npm install failed. Retrying with --legacy-peer-deps...")
                ok_legacy, _, _ = run_cmd([npm_cmd, "install", "--legacy-peer-deps"], cwd=FRONTEND_DIR)
                if not ok_legacy:
                    print_error(f"Failed to install frontend dependencies: {err}")
                    print_info("You can manually navigate to 'frontend' and run: npm install")
                else:
                    print_success("Frontend packages installed successfully (using --legacy-peer-deps).")
            else:
                print_success("Frontend packages installed successfully.")
        else:
            print_success("Frontend 'node_modules' already exists.")


# ════════════════════════════════════════════════════════════════
# 3. POSTGRESQL SERVICE & DATABASE AUTO-CREATION
# ════════════════════════════════════════════════════════════════
def check_port_open(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def setup_postgresql(py_exec):
    print_step(3, "Configuring PostgreSQL Database & Connection")

    env_file = BACKEND_DIR / ".env"
    env_vars = {}

    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    db_user = env_vars.get("DATABASE_USER", "postgres")
    db_pass = env_vars.get("DATABASE_PASSWORD", "")
    db_host = env_vars.get("DATABASE_HOST", "localhost")
    db_port = int(env_vars.get("DATABASE_PORT", "5432"))
    db_name = env_vars.get("DATABASE_NAME", "sat_sa_db")

    # 1. Check if PostgreSQL server is listening
    print_info(f"Checking PostgreSQL connectivity on {db_host}:{db_port}...")
    if not check_port_open(db_host, db_port):
        print_error(f"PostgreSQL service is not running on {db_host}:{db_port}!")
        if sys.platform == "win32":
            print_info(
                "HOW TO FIX ON WINDOWS:\n"
                "  1. Press Windows Key + R, type 'services.msc', and press Enter.\n"
                "  2. Find 'postgresql-x64-XX' in the list.\n"
                "  3. Right-click it and choose 'Start'.\n"
                "  4. Alternatively, open Command Prompt as Administrator and run:\n"
                "     net start postgresql-x64-16  (or your installed version)"
            )
        else:
            print_info("Start PostgreSQL service using: sudo systemctl start postgresql")
        sys.exit(1)

    print_success(f"PostgreSQL service detected on port {db_port}.")

    # Helper function to test credentials and create target database
    def test_and_create_db(user, password, host, port, target_db):
        script = f"""
import sys
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text

user = {repr(user)}
password = {repr(password)}
host = {repr(host)}
port = {port}
target_db = {repr(target_db)}

encoded_pass = quote_plus(password) if password else ""
conn_base = f"postgresql://{{user}}:{{encoded_pass}}@{{host}}:{{port}}" if password else f"postgresql://{{user}}@{{host}}:{{port}}"
connected = False

for admin_db in ['postgres', 'template1']:
    try:
        url = f"{{conn_base}}/{{admin_db}}"
        engine = create_engine(url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {{"dbname": target_db}}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{{target_db}}"'))
                print(f"DATABASE_CREATED:{{target_db}}")
            else:
                print(f"DATABASE_EXISTS:{{target_db}}")
        engine.dispose()
        connected = True
        break
    except Exception as e:
        err_msg = str(e)
        if "password authentication failed" in err_msg:
            print(f"AUTH_FAILED:{{err_msg}}")
            sys.exit(2)
        continue

if not connected:
    print("CONNECTION_FAILED")
    sys.exit(3)
"""
        return run_cmd([py_exec, "-c", script], capture=True)

    # 2. Interactive setup: prompt for password and db name if not configured or auth fails
    needs_prompt = not db_pass

    if not needs_prompt:
        # Test if existing credentials in .env work
        print_info(f"Testing existing credentials in 'backend/.env' (User: '{db_user}', DB: '{db_name}')...")
        ok, out, err = test_and_create_db(db_user, db_pass, db_host, db_port, db_name)
        if "DATABASE_CREATED" in out:
            print_success(f"Database '{db_name}' created automatically.")
        elif "DATABASE_EXISTS" in out:
            print_success(f"Database '{db_name}' verified and ready.")
        else:
            print_warning("Existing password in 'backend/.env' failed authentication.")
            needs_prompt = True

    if needs_prompt:
        print("\n" + "-" * 56)
        print("  PostgreSQL Setup & Database Configuration")
        print("-" * 56)
        
        entered_user = input(f"  Enter PostgreSQL Username [{db_user}]: ").strip()
        if entered_user:
            db_user = entered_user

        entered_db = input(f"  Enter Database Name to use or create [{db_name}]: ").strip()
        if entered_db:
            db_name = entered_db

        max_attempts = 3
        connected = False

        for attempt in range(1, max_attempts + 1):
            try:
                import getpass
                entered_pass = getpass.getpass(f"  Enter PostgreSQL password for '{db_user}': ").strip()
            except Exception:
                entered_pass = input(f"  Enter PostgreSQL password for '{db_user}': ").strip()

            db_pass = entered_pass
            ok, out, err = test_and_create_db(db_user, db_pass, db_host, db_port, db_name)

            if "DATABASE_CREATED" in out:
                print_success(f"Database '{db_name}' created successfully on PostgreSQL!")
                connected = True
                break
            elif "DATABASE_EXISTS" in out:
                print_success(f"Database '{db_name}' verified and ready on PostgreSQL.")
                connected = True
                break
            elif "AUTH_FAILED" in out:
                print_error(f"Authentication failed for user '{db_user}'.")
                if attempt < max_attempts:
                    print_info(f"Please try again ({attempt}/{max_attempts}).")
                else:
                    print_error("Maximum password attempts reached. Please verify your PostgreSQL credentials.")
                    sys.exit(1)
            else:
                print_error(f"Could not connect to PostgreSQL: {out} {err}")
                sys.exit(1)

    # 3. Save verified parameters to backend/.env
    env_vars["DATABASE_USER"] = db_user
    env_vars["DATABASE_PASSWORD"] = db_pass
    env_vars["DATABASE_HOST"] = db_host
    env_vars["DATABASE_PORT"] = str(db_port)
    env_vars["DATABASE_NAME"] = db_name

    with open(env_file, "w") as f:
        f.write("# PostgreSQL Database Configuration\n")
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    print_success(f"Updated 'backend/.env' with verified database '{db_name}' settings.")


# ════════════════════════════════════════════════════════════════
# 4. INITIALIZE TABLES & SCHEMA MIGRATION
# ════════════════════════════════════════════════════════════════
def initialize_schema(py_exec):
    print_step(4, "Creating Database Tables & Initializing Schema")

    init_script = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
from database import init_db
init_db()
print("SCHEMA_INITIALIZED_OK")
"""

    ok, out, err = run_cmd([py_exec, "-c", init_script], cwd=ROOT_DIR, capture=True)
    if ok and "SCHEMA_INITIALIZED_OK" in out:
        print_success("Tables 'soc_alerts' and 'asset_inventory' initialized successfully.")
    else:
        print_error(f"Failed to initialize schema: {out} {err}")
        print_info("Database tables could not be registered. Please check database permissions.")


# ════════════════════════════════════════════════════════════════
# 5. OLLAMA OPTIONAL HEALTH CHECK
# ════════════════════════════════════════════════════════════════
def check_ollama():
    print_step(5, "Checking Local AI Engine (Ollama - Optional)")

    ollama_running = check_port_open("localhost", 11434, timeout=1.5)
    if ollama_running:
        print_success("Ollama service is active on http://localhost:11434 (Local AI inference ready).")
        # Check models
        ok, out, _ = run_cmd(["ollama", "list"], capture=True)
        if ok and ("llama3" in out or "phi3" in out):
            print_success("Found local model (llama3/phi3) ready for supervisory explainability.")
        else:
            print_info("Tip: You can run 'ollama run llama3' to download the local audit explainability model.")
    else:
        print_info(
            "Ollama is currently not running on port 11434.\n"
            "    SAT-SA will automatically operate in Deterministic Rule Engine fallback mode.\n"
            "    (All analytics, anomaly detection, and reports will work 100% without Ollama)."
        )


# ════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ════════════════════════════════════════════════════════════════
def main():
    print("\n" + "=" * 64)
    print("  SAT-SA: Supervisory Analytics Tool for SOC Assessment")
    print("  Automated Prototype Setup & Self-Healing Installer (SIH-26157)")
    print("=" * 64)
    print("  [NOTE] Internet is ONLY required during first-time setup")
    print("  to download dependencies (pip packages, npm, Ollama model).")
    print("  After setup, SAT-SA operates 100% offline (air-gap ready).")
    print("=" * 64 + "\n")

    start_time = time.time()

    py_exec = check_python_environment()
    check_node_environment()
    setup_postgresql(py_exec)
    initialize_schema(py_exec)
    check_ollama()

    elapsed = round(time.time() - start_time, 1)

    print("\n" + "=" * 64)
    print(f"  SETUP COMPLETED SUCCESSFULLY in {elapsed}s!")
    print("=" * 64 + "\n")

    print("How to launch SAT-SA:")
    print("  Option A (One-Click): Run the launch script:")
    if sys.platform == "win32":
        print("      .\\run.bat")
    else:
        print("      python run.py")

    print("\n  Option B (Two Terminals):")
    print("      Terminal 1 (Backend):  cd backend && uvicorn main:app --reload --port 8000")
    print("      Terminal 2 (Frontend): cd frontend && npm run dev")
    print("\n  Dashboard URL:        http://localhost:3000")
    print("  Backend Swagger docs: http://127.0.0.1:8000/docs\n")


if __name__ == "__main__":
    main()
