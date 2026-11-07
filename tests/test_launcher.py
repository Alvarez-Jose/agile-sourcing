"""Exercise launcher process ownership without opening browsers or binding ports."""

import io
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest

SOURCE = (Path(__file__).resolve().parents[1] / "run.sh").read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


@pytest.fixture
def project(tmp_path):
    for folder in ("secret", "frontend/node_modules/.bin", "backend/rag", "data/raw_policies"):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "frontend/node_modules/.bin/wxt").touch()
    (tmp_path / "secret/.env").write_text("\n".join(
        f"{key}=fixture" for key in (
            "VITE_FIREBASE_API_KEY", "VITE_FIREBASE_AUTH_DOMAIN", "VITE_FIREBASE_PROJECT_ID",
            "VITE_FIREBASE_APP_ID", "VITE_GOOGLE_CLIENT_ID",
        )
    ))
    (tmp_path / "backend/rag/pipeline.py").write_text(
        "CHROMA_DIR = 'data/index'\nCOLLECTION_NAME = 'uc_policies'\nLLM_MODEL = 'qwen3:8b'\n"
    )
    (tmp_path / "data/index").mkdir()
    with sqlite3.connect(tmp_path / "data/index/chroma.sqlite3") as db:
        db.execute("CREATE TABLE collections (name TEXT)")
        db.execute("INSERT INTO collections VALUES ('uc_policies')")
    (tmp_path / "data/raw_policies/demo.pdf").touch()
    return tmp_path


def run_launcher(project, *, args=(), existing_ollama=True, model_present=True, backend_fails=False):
    processes = []
    kills = []
    calls = []
    requests = []

    class Process:
        def __init__(self, command, **kwargs):
            self.command = command
            self.pid = 10000 + len(processes)
            self.returncode = None
            assert kwargs["start_new_session"] is True
            processes.append(self)

        def poll(self):
            return 1 if backend_fails and "uvicorn" in self.command else None

        def wait(self, **kwargs):
            calls.append(self.command)
            return 0

    def urlopen(url, **kwargs):
        requests.append(url)
        if len(requests) == 1 and not existing_ollama:
            raise OSError("No server")
        payload = {"models": [{"name": "qwen3:8b"}] if model_present else []}
        return io.StringIO(json.dumps(payload))

    def interrupt_after_startup(_):
        raise KeyboardInterrupt

    with patch("sys.argv", ["run.sh", str(project), *args]), \
         patch.dict("os.environ", {}, clear=True), \
         patch("os.chdir"), \
         patch("importlib.util.find_spec", return_value=object()), \
         patch("shutil.which", side_effect=lambda name: "/fake/" + name), \
         patch("subprocess.check_output", return_value="22.23.0"), \
         patch("subprocess.Popen", side_effect=Process), \
         patch("socket.socket") as socket, \
         patch("urllib.request.urlopen", side_effect=urlopen), \
         patch("time.sleep", side_effect=interrupt_after_startup), \
         patch("signal.signal"), \
         patch("os.killpg", side_effect=lambda pid, sig: kills.append((pid, sig))):
        socket.return_value.__enter__.return_value.connect_ex.return_value = 1
        try:
            exec(compile(SOURCE, "run.sh", "exec"), {"__name__": "__main__"})
        except SystemExit as error:
            error.launcher_processes = processes
            error.launcher_kills = kills
            raise
    return processes, kills, calls


def test_existing_ollama_is_reused_and_only_owned_process_groups_are_stopped(project):
    processes, kills, _ = run_launcher(project)
    assert len(processes) == 2
    assert "uvicorn" in processes[0].command
    assert processes[1].command == ["corepack", "pnpm", "dev"]
    assert {pid for pid, sig in kills} == {p.pid for p in processes}
    assert all((p.pid, signal.SIGTERM) in kills for p in processes)


def test_environment_model_slots_are_read_without_importing_ml(project):
    (project / "backend/rag/pipeline.py").write_text(
        "import os\nCHROMA_DIR = 'data/index'\n"
        "COLLECTION_NAME = os.environ.get('CHROMA_COLLECTION', 'uc_policies')\n"
        "LLM_MODEL = os.environ.get('LLM_MODEL', 'qwen3:8b')\n"
    )
    with (project / "secret/.env").open("a") as stream:
        stream.write("\nCHROMA_COLLECTION=custom_index\nLLM_MODEL=custom-model\n")
    with sqlite3.connect(project / "data/index/chroma.sqlite3") as db:
        db.execute("UPDATE collections SET name='custom_index'")
    processes, _, _ = run_launcher(project)
    assert ["ollama", "pull", "custom-model"] in [p.command for p in processes]


def test_missing_ollama_is_started_and_stopped_with_launcher(project):
    processes, kills, _ = run_launcher(project, existing_ollama=False)
    assert processes[0].command == ["ollama", "serve"]
    assert (processes[0].pid, signal.SIGTERM) in kills
    assert len(processes) == 3


def test_explicit_index_and_missing_model_finish_before_backend_starts(project):
    processes, kills, waited = run_launcher(project, args=("--index",), model_present=False)
    assert processes[0].command == ["ollama", "pull", "qwen3:8b"]
    assert processes[1].command == [sys.executable, "-m", "scripts.ingest_policies", "--ingest"]
    assert waited[:2] == [processes[0].command, processes[1].command]
    assert not {processes[0].pid, processes[1].pid} & {pid for pid, sig in kills}


def test_setup_check_starts_no_services(project):
    with pytest.raises(SystemExit) as error:
        run_launcher(project, args=("--check",))
    assert error.value.code == 0
    assert error.value.launcher_processes == []


def test_backend_failure_does_not_launch_frontend_and_cleans_up(project):
    with pytest.raises(SystemExit, match="backend stopped") as error:
        run_launcher(project, backend_fails=True)
    processes = error.value.launcher_processes
    assert len(processes) == 1
    assert "uvicorn" in processes[0].command
    assert (processes[0].pid, signal.SIGTERM) in error.value.launcher_kills


def test_missing_index_stops_before_any_service_or_download(project):
    with sqlite3.connect(project / "data/index/chroma.sqlite3") as db:
        db.execute("DELETE FROM collections")
    with pytest.raises(SystemExit, match="main policy index is missing") as error:
        run_launcher(project)
    assert error.value.launcher_processes == []


def shell_launcher(tmp_path, *, local_name=None, active=None):
    root = tmp_path / "project with spaces"
    root.mkdir()
    launcher = root / "run.sh"
    launcher.write_text((Path(__file__).resolve().parents[1] / "run.sh").read_text())
    for environment in filter(None, (root / local_name if local_name else None, active)):
        (environment / "bin").mkdir(parents=True)
        python = environment / "bin/python"
        # Stand in for Python so these checks never import models or start services.
        python.write_text('#!/bin/bash\nprintf "ENV=%s\\n" "$VIRTUAL_ENV"\n')
        python.chmod(0o755)
        (environment / "bin/activate").write_text(f'export VIRTUAL_ENV="{environment}"\n')
    env = {"PATH": os.defpath}
    if active:
        env["VIRTUAL_ENV"] = str(active)
    return root, subprocess.run(["bash", str(launcher), "--check"], env=env,
                               cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.parametrize("name", ["venv", ".venv", "env", ".env"])
def test_shell_finds_local_environment_from_another_directory(tmp_path, name):
    root, result = shell_launcher(tmp_path, local_name=name)
    assert result.returncode == 0, result.stderr
    assert f"ENV={root / name}" in result.stdout


def test_shell_prefers_active_environment_over_local_one(tmp_path):
    active = tmp_path / "existing environment"
    _, result = shell_launcher(tmp_path, local_name="venv", active=active)
    assert result.returncode == 0, result.stderr
    assert f"ENV={active}" in result.stdout
    assert "Activating local" not in result.stdout


def test_shell_without_environment_stops_with_instructions(tmp_path):
    root, result = shell_launcher(tmp_path)
    assert result.returncode == 1
    assert "run ./run.sh to create venv/" in result.stderr
    assert not (root / "venv").exists()


def test_shell_bootstrap_installs_into_new_environment_and_then_launches(tmp_path):
    root = tmp_path / "fresh clone"
    (root / "frontend").mkdir(parents=True)
    launcher = root / "run.sh"
    launcher.write_text((Path(__file__).resolve().parents[1] / "run.sh").read_text())
    tools = tmp_path / "tools"
    tools.mkdir()
    log = tmp_path / "commands.log"
    # These stand-ins record installation commands without network access.
    python = tools / "python3.12"
    python.write_text('''#!/bin/bash
if [[ "$1" == "-c" ]]; then exit 0; fi
mkdir -p "$3/bin"
printf 'export VIRTUAL_ENV="%s"\\n' "$3" > "$3/bin/activate"
cp "$TEST_TOOLS/venv-python" "$3/bin/python"
''')
    (tools / "venv-python").write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_LOG"
''')
    (tools / "corepack").write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_LOG"
''')
    for tool in tools.iterdir():
        tool.chmod(0o755)
    result = subprocess.run(["bash", str(launcher)], cwd=tmp_path,
                            env={"PATH": f"{tools}:{os.defpath}", "TEST_TOOLS": str(tools),
                                 "TEST_LOG": str(log)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert calls == [f"-m pip install -r {root / 'requirements.txt'}", "-m pip check",
                     "pnpm install --frozen-lockfile", f"- {root}"]
    assert (root / "venv/bin/python").is_file()
