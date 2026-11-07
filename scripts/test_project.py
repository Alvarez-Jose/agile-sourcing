"""Grouped project checks. Run ./test.sh --help from any directory."""

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from evaluation.progress import Progress

ROOT = Path(__file__).resolve().parents[1]


def run_pytest(paths):
    import pytest

    class Results:
        outcomes = {}
        collection_errors = 0

        def pytest_collectreport(self, report):
            if report.failed:
                self.collection_errors += 1

        def pytest_runtest_logreport(self, report):
            previous = self.outcomes.get(report.nodeid)
            if report.failed:
                self.outcomes[report.nodeid] = "failed" if report.when == "call" else "error"
            elif previous not in ("failed", "error") and (report.when == "call" or report.skipped):
                self.outcomes[report.nodeid] = report.outcome

    results = Results()
    code = int(pytest.main([*paths, "-q", "-rs"], plugins=[results]))
    counts = Counter(results.outcomes.values())
    counts["error"] += results.collection_errors
    evaluated = counts["passed"] + counts["failed"] + counts["error"]
    print(f"\nTest report: {counts['passed']} passed, {counts['failed']} failed, "
          f"{counts['error']} errors, {counts['skipped']} skipped.")
    if evaluated:
        print(f"Pass rate: {counts['passed'] / evaluated:.1%} of executed tests (skips excluded).")
    sys.stdout.flush()
    return code


def frontend(auth_only=False):
    pnpm = ["corepack", "pnpm"] if shutil.which("corepack") else ["pnpm"]
    if not shutil.which(pnpm[0]):
        raise RuntimeError("Install Node/Corepack and the frontend dependencies; see README.md.")
    steps = ([['exec', 'node', '--test', 'tests/auth.test.cjs', 'tests/agent.test.cjs']]
             if auth_only else [["test"], ["compile"], ["build"]])
    for i, step in enumerate(steps, 1):
        print(f"\nFrontend check {i}/{len(steps)}: {' '.join(step)}", flush=True)
        completed = subprocess.run(pnpm + step, cwd=ROOT / "frontend")
        if completed.returncode:
            print(f"Frontend report: check {i}/{len(steps)} failed; later checks were not run.")
            return completed.returncode
    print(f"\nFrontend report: {len(steps)}/{len(steps)} checks passed. "
          "Test counts are printed above; this is not browser sign-in validation.")
    return 0


def health(base_url):
    url = base_url.rstrip("/") + "/api/health"
    start = time.monotonic()
    try:
        with urlopen(url, timeout=5) as response:
            status, body = response.status, json.load(response)
    except (URLError, OSError, ValueError) as error:
        print(f"Health report: FAIL — {url}: {error}")
        return 1
    passed = status == 200 and isinstance(body, dict) and body.get("status") == "ok"
    print(f"Health report: {'PASS' if passed else 'FAIL'} — HTTP {status}, "
          f"{(time.monotonic() - start) * 1000:.0f} ms; {url}")
    print("Checks API availability only; it does not test login, the index, or model answers.")
    return 0 if passed else 1


def grade_responses(rows, judge, progress=None):
    for i, row in enumerate(rows, 1):
        try:
            # Runtime failures must never be graded as successful answers.
            row["judge_grade"] = "wrong" if row.get("error") else judge(row)
            row["judge_error"] = None
        except Exception as error:
            row["judge_grade"] = None
            row["judge_error"] = str(error)
        if progress:
            progress(i)
    return rows


def quality_summary(rows):
    from evaluation.summarize_grounding import summarize_responses

    grades = Counter(row.get("judge_grade") for row in rows)
    latencies = [row["latency_seconds"] for row in rows]
    return {"questions": len(rows), "correct": grades["correct"],
            "partial": grades["partial"], "wrong": grades["wrong"],
            "ungraded": grades[None], "judge_accuracy": grades["correct"] / len(rows),
            "empty_answers": sum(not row.get("answer", "").strip() for row in rows),
            "mean_seconds": statistics.mean(latencies),
            "median_seconds": statistics.median(latencies),
            "grounding": dict(summarize_responses(rows))}


def rag(args, output):
    from evaluation.benchmarks.run_grounding_benchmark import run_questions, save_results
    from evaluation.metrics.score import JUDGE_MODEL, score_judge
    import ollama

    output.mkdir(parents=True, exist_ok=True)
    questions = json.loads((ROOT / "evaluation/results/benchmark_questions_corrected.json").read_text())["questions"][:args.limit]
    log_path = output / "model.log"
    print(f"Results and model logs: {output}", flush=True)
    # Keep the heartbeat visible while verbose model loaders/retrieval log to disk.
    terminal = sys.stdout
    with log_path.open("w") as log:
        with Progress("Loading models and checking index", stream=terminal), redirect_stdout(log), redirect_stderr(log):
            ollama.Client(timeout=10).list()
            from backend.rag.pipeline import ask, get_collection, EMBED_MODEL, LLM_MODEL, COLLECTION_NAME
            if get_collection() is None:
                raise RuntimeError("Policy index is missing. Review the intended documents and run ./run.sh --index.")
        print(f"Answer model: {LLM_MODEL}; embedder: {EMBED_MODEL}; collection: {COLLECTION_NAME}")
        print(f"Judge: {args.judge_model or JUDGE_MODEL}; corrected answer key; {len(questions)} questions.")
        print(f"Model logs: {log_path}")
        with Progress("Answering", len(questions), terminal) as progress, redirect_stdout(log), redirect_stderr(log):
            rows = run_questions(questions, ask, output / "responses.json", progress.update)
        with Progress("Grading", len(rows), terminal) as progress, redirect_stdout(log), redirect_stderr(log):
            def judged(row):
                return score_judge(row, model=args.judge_model or JUDGE_MODEL)

            def checkpoint(i):
                save_results(output / "graded_responses.json", rows)
                progress.update(i)

            grade_responses(rows, judged, checkpoint)
    summary = quality_summary(rows)
    summary.update({"answer_model": LLM_MODEL, "embed_model": EMBED_MODEL,
                    "collection": COLLECTION_NAME, "judge_model": args.judge_model or JUDGE_MODEL,
                    "answer_key": "benchmark_questions_corrected.json"})
    save_results(output / "summary.json", summary)
    g = summary["grounding"]
    print(f"\nRAG report ({summary['questions']} questions)")
    print(f"LLM-judged accuracy: {summary['correct']}/{summary['questions']} = {summary['judge_accuracy']:.1%}")
    print(f"Correct: {summary['correct']} | Partial: {summary['partial']} | "
          f"Incorrect: {summary['wrong']} | Ungraded: {summary['ungraded']}")
    print(f"Execution errors: {g['execution_errors']} | Empty answers: {summary['empty_answers']} | Refusals: {g['refusals']}")
    print(f"Invalid citation IDs: {g['invalid_citations']} | Empty cited evidence: {g['empty_evidence']}")
    print(f"Amount-review flags: {g['unmatched_dollar_amounts']} "
          f"(including question-supplied amounts: {g['question_amounts_not_in_evidence']})")
    print(f"Latency: mean {summary['mean_seconds']:.1f}s, median {summary['median_seconds']:.1f}s")
    print("Automated judge estimates only; citation checks and grades do not prove policy correctness.")
    print(f"Results: {output}")
    return 1 if g["execution_errors"] or summary["ungraded"] or summary["empty_answers"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="./test.sh", description="One command per test group; long model checks are opt-in.")
    parser.add_argument("group", choices=["all", "backend", "auth", "frontend", "cart", "health", "rag", "retrieval"])
    parser.add_argument("--limit", type=int, default=60, help="RAG/retrieval questions (1–60; default: 60)")
    parser.add_argument("--url", default="http://localhost:8000", help="Base API URL for health")
    parser.add_argument("--judge-model", help="Installed Ollama judge model for RAG; default JUDGE_MODEL or qwen3:8b")
    parser.add_argument("--output-dir", type=Path, help="New directory for model-check results")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 60:
        parser.error("--limit must be between 1 and 60")
    os.chdir(ROOT)
    try:
        if args.group == "health":
            return health(args.url)
        if args.group == "frontend":
            return frontend()
        if args.group == "auth":
            backend_code = run_pytest(["tests/integration/test_auth.py"])
            frontend_code = frontend(auth_only=True)
            print(f"\nAuth report: backend {'FAIL' if backend_code else 'PASS'}, "
                  f"frontend {'FAIL' if frontend_code else 'PASS'} (simulated service/browser boundaries).")
            return 1 if backend_code or frontend_code else 0
        if args.group == "backend":
            return run_pytest(["rules", "tests"])
        if args.group == "all":
            backend_code = run_pytest(["rules", "tests"])
            frontend_code = frontend()
            print(f"\nQuick suite: backend {'FAIL' if backend_code else 'PASS'}, "
                  f"frontend {'FAIL' if frontend_code else 'PASS'}.")
            return 1 if backend_code or frontend_code else 0
        if args.group == "cart":
            code = run_pytest(["tests/integration/test_cart_guide.py"])
            if code:
                return code
            return subprocess.run([sys.executable, "-m", "scripts.evaluate_cart_demo"], cwd=ROOT).returncode
        from dotenv import load_dotenv
        load_dotenv(ROOT / "secret/.env")
        output = args.output_dir or ROOT / "data/evaluation" / (args.group + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        if output.exists():
            raise RuntimeError(f"Output directory already exists; choose a new directory: {output}")
        if args.group == "rag":
            return rag(args, output)
        output.mkdir(parents=True)
        return subprocess.run([sys.executable, "-m", "evaluation.metrics.retrieval_recall",
                               "--limit", str(args.limit), "--top-k", "5", "--out", str(output / "retrieval.json")], cwd=ROOT).returncode
    except KeyboardInterrupt:
        print("\nStopped.")
        if args.group == "rag":
            print("Completed RAG answers/grades are saved in the results directory.")
        return 130
    except Exception as error:
        print(f"\nCheck failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
