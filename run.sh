#!/usr/bin/env bash
# Launch the local backend, Ollama, and WXT from any working directory.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$PROJECT_ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing venv. Follow README first-time setup (Python 3.12+) before running this file." >&2
  exit 1
fi
exec "$PYTHON" - "$PROJECT_ROOT" "$@" <<'PY'
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

root = Path(sys.argv.pop(1))
parser = argparse.ArgumentParser(prog="run.sh", description="Run Agile Sourcing locally. Ctrl+C stops services started here.")
parser.add_argument("--check", action="store_true", help="Check setup without starting services or downloading anything")
parser.add_argument("--index", action="store_true", help="Rebuild the main index from the intended PDF/DOCX corpus before starting")
args = parser.parse_args()
if args.check and args.index:
    parser.error("Use --check or --index separately")
os.chdir(root)

def fail(message):
    raise SystemExit(message)

if sys.version_info < (3, 12):
    fail("Python 3.12+ is required. Follow the README environment setup.")
missing = [name for name in ("uvicorn", "fastapi", "firebase_admin", "dotenv", "ollama",
                           "chromadb", "sentence_transformers", "pdfplumber", "docx")
           if importlib.util.find_spec(name) is None]
if missing:
    fail("Missing Python dependencies: " + ", ".join(missing) +
         "\nRun: ./venv/bin/python -m pip install -r requirements.txt")
for tool in ("node", "ollama"):
    if not shutil.which(tool):
        fail(f"Missing {tool}. Install it using the README first-time setup.")
node = subprocess.check_output(["node", "-p", "process.versions.node"], text=True).strip()
if tuple(map(int, node.split(".")[:2])) < (22, 13):
    fail(f"Node {node} is too old. Select Node 22.13+ before starting.")
pnpm = ["corepack", "pnpm"] if shutil.which("corepack") else ["pnpm"]
if not shutil.which(pnpm[0]):
    fail("Install Corepack or pnpm as described in the README.")
if not (root / "frontend/node_modules/.bin/wxt").exists():
    fail("Frontend dependencies are missing. Run: cd frontend && corepack pnpm install --frozen-lockfile")

# Parse dotenv as data, never execute it as a shell script or print its values.
from dotenv import dotenv_values
secret = root / "secret"
if not (secret / ".env").is_file():
    fail("Missing secret/.env. Configure Firebase using docs/auth-setup.md.")
config = {**dotenv_values(secret / ".env"), **os.environ}
required = ("VITE_FIREBASE_API_KEY", "VITE_FIREBASE_AUTH_DOMAIN", "VITE_FIREBASE_PROJECT_ID",
            "VITE_FIREBASE_APP_ID", "VITE_GOOGLE_CLIENT_ID")
missing = [key for key in required if not config.get(key)]
if missing:
    fail("Missing Firebase configuration keys: " + ", ".join(missing))
credential = config.get("GOOGLE_APPLICATION_CREDENTIALS")
if credential:
    credential = Path(credential).expanduser()
    if not credential.is_absolute():
        credential = secret / credential
    if not credential.is_file():
        fail("The Admin credential file configured by GOOGLE_APPLICATION_CREDENTIALS does not exist.")
# Without a configured credential file, the backend can use existing ADC.
api = urllib.parse.urlparse(config.get("VITE_API_BASE_URL") or "http://localhost:8000")
if api.scheme != "http" or api.hostname not in ("localhost", "127.0.0.1") or api.port != 8000 or api.path.rstrip("/"):
    fail("For this local launcher, set VITE_API_BASE_URL=http://localhost:8000 in secret/.env.")

# Follow the teammate pipeline's configured collection/model without importing ML.
constants = {}
for statement in ast.parse((root / "backend/rag/pipeline.py").read_text()).body:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        name = getattr(statement.targets[0], "id", "")
        if name in ("CHROMA_DIR", "COLLECTION_NAME", "LLM_MODEL"):
            constants[name] = ast.literal_eval(statement.value)
database = root / constants["CHROMA_DIR"] / "chroma.sqlite3"
indexed = False
if database.is_file():
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            indexed = bool(db.execute("SELECT 1 FROM collections WHERE name=?",
                                      (constants["COLLECTION_NAME"],)).fetchone())
    except sqlite3.Error:
        pass
if not indexed and not args.index:
    fail("The main policy index is missing. Review the intended documents in data/raw_policies, "
         "then run ./run.sh --index once. This indexes every top-level PDF/DOCX there; "
         "do not include held documents without authorization.")
if args.index and not any(p.is_file() and p.suffix.lower() in (".pdf", ".docx")
                          for p in (root / "data/raw_policies").glob("*")):
    fail("No policy PDFs/DOCX found. Add the intended corpus or run the README starter downloader first.")
print(f"Setup checks passed (Python {sys.version.split()[0]}, Node {node}).", flush=True)
if args.check:
    print("Configuration files and index found. Firebase login and live model answers are not tested by --check.")
    raise SystemExit(0)

with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", 8000)) == 0:
        fail("Port 8000 is already in use. Stop the existing backend before running this launcher.")
logs = Path(tempfile.mkdtemp(prefix="agile-sourcing-"))
children = []

def start(name, command, cwd=root):
    log = (logs / f"{name}.log").open("w")
    try:
        process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    finally:
        log.close()
    children.append((name, process))
    return process

def fetch(url):
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.load(response)

def wait_ready(name, process, url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"{name} stopped. See {logs / (name + '.log')}")
        try:
            return fetch(url)
        except (OSError, ValueError):
            time.sleep(0.5)
    fail(f"{name} did not become ready within {timeout}s. See {logs / (name + '.log')}")

def interrupt(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, interrupt)
try:
    ollama_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not ollama_url.startswith(("http://", "https://")):
        ollama_url = "http://" + ollama_url
    try:
        tags = fetch(ollama_url + "/api/tags")
        print("Using the existing Ollama service.", flush=True)
    except (OSError, ValueError):
        print("Starting Ollama...", flush=True)
        service = start("ollama", ["ollama", "serve"])
        tags = wait_ready("ollama", service, ollama_url + "/api/tags")
    model = constants["LLM_MODEL"]
    if not any(item.get("name") == model for item in tags.get("models", [])):
        print(f"Downloading {model} (first run only; several GB)...", flush=True)
        download = start("model-download", ["ollama", "pull", model])
        if download.wait() != 0:
            fail(f"Model download failed. See {logs / 'model-download.log'}")
        children.remove(("model-download", download))
    if args.index:
        print("Rebuilding the policy index from data/raw_policies; this can take several minutes...", flush=True)
        indexing = start("indexing", [sys.executable, "-m", "scripts.ingest_policies", "--ingest"])
        if indexing.wait() != 0:
            fail(f"Indexing failed; services will stop. See {logs / 'indexing.log'}")
        children.remove(("indexing", indexing))
    backend = start("backend", [sys.executable, "-m", "uvicorn", "backend.main:app", "--reload",
                                "--host", "127.0.0.1", "--port", "8000"])
    wait_ready("backend", backend, "http://127.0.0.1:8000/api/health")
    start("frontend", pnpm + ["dev"], root / "frontend")
    print(f"Backend ready: http://localhost:8000/api/health\n"
          f"Starting the extension development browser. Logs: {logs}\n"
          "Sign in with Google; account approval is still required.\n"
          "Health checks do not guarantee chat readiness; models may load on the first question.\n"
          "Keep this terminal open. Press Ctrl+C to stop services started here.", flush=True)
    while True:
        for name, process in children:
            if process.poll() is not None:
                fail(f"{name} exited ({process.returncode}). See {logs / (name + '.log')}")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nStopping services started by this launcher...", flush=True)
finally:
    # Process groups also include Uvicorn's reload workers and WXT child processes.
    # An existing Ollama service was not added to children and is left running.
    for name, process in reversed(children):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 3
    for name, process in children:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for name, process in children:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
PY
