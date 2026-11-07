#!/usr/bin/env bash
# One entry point for project tests, using the project's virtual environment.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$PROJECT_DIR/venv/bin/python" ]]; then
  echo "Create venv and install requirements first; see README.md." >&2
  exit 1
fi
cd "$PROJECT_DIR"
exec "$PROJECT_DIR/venv/bin/python" -m scripts.test_project "$@"
