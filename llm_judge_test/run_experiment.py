# llm_judge_test/run_experiment.py
# freeze RAG answers, then independently grade each with three models three times.
# run: python -m llm_judge_test.run_experiment --help
import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from evaluation.progress import Progress
from llm_judge_test.common import SCHEMA, RUBRIC, fingerprint, judge_prompt, parse_grade, save_csv, save_json


DEFAULT_MODELS = ["qwen3:8b", "gemma4:12b", "llama3:8b"]
KEY = ROOT / "evaluation/results/benchmark_questions_corrected.json"
REPEATS = 3
DETAIL_FIELDS = ["question_id", "question", "reference_answer", "rag_answer", "model", "run",
                 "grade", "explanation", "status", "error", "seed", "temperature", "latency_seconds"]


def checkpoint(directory, state):
    save_json(directory / "experiment.json", state)
    save_json(directory / "responses.json", state["responses"])
    answers = {row["question_id"]: row for row in state["responses"]}
    details = []
    for judgment in state["judgments"]:
        answer = answers[judgment["question_id"]]
        details.append({**judgment, "question": answer["question"],
                        "reference_answer": answer["ground_truth"], "rag_answer": answer["system_answer"]})
    save_csv(directory / "judgments.csv", details, DETAIL_FIELDS)


def grade_once(client, model, response, run, *, temperature, seed, thinking):
    record = {"question_id": response["question_id"], "model": model, "run": run,
              "seed": seed, "temperature": temperature, "grade": None, "explanation": "",
              "status": "error", "error": None, "raw_response": ""}
    started = time.monotonic()
    answer = response["system_answer"].strip()
    if response.get("error") or not answer or answer.startswith("ERROR:"):
        record.update(status="skipped_rag_error", error="No valid RAG answer to judge")
        record["latency_seconds"] = 0
        return record
    try:
        kwargs = {"think": False} if thinking else {}
        result = client.chat(
            model=model, messages=[{"role": "user", "content": judge_prompt(response)}],
            format=SCHEMA, stream=False, keep_alive="5m",
            options={"temperature": temperature, "seed": seed, "num_predict": 512, "num_ctx": 8192},
            **kwargs,
        )
        record["raw_response"] = result["message"]["content"]
        record["done_reason"] = result.get("done_reason")
        record["prompt_eval_count"] = result.get("prompt_eval_count")
        record["eval_count"] = result.get("eval_count")
        if record["done_reason"] == "length":
            raise ValueError("Judge response hit the token limit")
        # Reject likely context saturation instead of silently grading a clipped input.
        if (record["prompt_eval_count"] or 0) >= 8192 - 512:
            raise ValueError("Judge input reached the configured context budget")
        record.update(parse_grade(record["raw_response"]), status="ok")
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["latency_seconds"] = round(time.monotonic() - started, 3)
    return record


def validate_responses(rows, questions):
    if len(rows) > len(questions):
        raise ValueError("Saved responses contain more questions than requested")
    for number, (row, question) in enumerate(zip(rows, questions), 1):
        if row.get("question") != question["question"] or row.get("ground_truth") != question["answer"]:
            raise ValueError(f"Saved question/reference does not match the corrected key at Q{number}")
        if not isinstance(row.get("system_answer"), str):
            raise ValueError(f"Missing saved answer at Q{number}")
        row["question_id"] = number


def retrieval_complete(path, count):
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return (len(rows) == count and [row["q"] for row in rows] == list(range(1, count + 1))
                and all(isinstance(row["hit_at_5"], bool) and isinstance(row["hit_in_pool"], bool) for row in rows))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / "secret/.env", override=False)
    os.chdir(ROOT)
    import ollama
    # Refuse cloud tags: this experiment is intended to use local open weights.
    if any("cloud" in model.lower() for model in args.models):
        raise ValueError("Use local model tags, not cloud models")
    client = ollama.Client(timeout=args.timeout)
    with Progress("Checking Ollama and local judges"):
        installed = {item.model: item for item in client.list().models}
        missing = [model for model in args.models if model not in installed]
        if missing:
            raise ValueError("Missing local judge models. Install them first:\n" +
                             "\n".join(f"  ollama pull {model}" for model in missing))
        model_info = {}
        for model in args.models:
            info = client.show(model).model_dump(mode="json")
            if info.get("remote_host") or info.get("remote_model"):
                raise ValueError(f"{model} points to a remote model; use local weights")
            model_info[model] = {"digest": installed[model].digest,
                                 "details": info.get("details"), "capabilities": info.get("capabilities") or []}
    if args.check:
        print("All three local judge tags are installed. No answers or judgments were generated.")
        return 0

    questions = json.loads(KEY.read_text(encoding="utf-8"))["questions"][:args.limit]
    config = {"models": args.models, "repeats": REPEATS, "temperature": args.temperature,
              "seed": args.seed, "timeout_seconds": args.timeout, "num_predict": 512,
              "num_ctx": 8192, "question_count": len(questions), "key_sha256": fingerprint(questions),
              "rubric_sha256": fingerprint(RUBRIC), "schema_sha256": fingerprint(SCHEMA)}
    if args.resume:
        directory = args.resume.resolve()
        state = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
        if state["metadata"]["config"] != config or state["metadata"]["judges"] != model_info:
            raise ValueError("Resume settings, answer key, or model digests differ from the saved experiment")
        validate_responses(state["responses"], questions)
    else:
        directory = (args.output_dir or ROOT / "llm_judge_test/results" /
                     datetime.now().strftime("%Y%m%d_%H%M%S_%f")).resolve()
        directory.mkdir(parents=True, exist_ok=False)
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        state = {"metadata": {"created_at": datetime.now(timezone.utc).isoformat(), "git_revision": revision,
                              "config": config, "judges": model_info, "answer_key": str(KEY.relative_to(ROOT)),
                              "judge_prompt": RUBRIC, "notes": "Reference agreement, not expert-validated correctness."},
                 "responses": [], "judgments": []}
        if args.responses:
            state["responses"] = json.loads(args.responses.resolve().read_text(encoding="utf-8"))
            if len(state["responses"]) != len(questions):
                raise ValueError("Reused responses must cover exactly the requested questions")
            validate_responses(state["responses"], questions)
        checkpoint(directory, state)
    print(f"Experiment: {directory}")
    print(f"{len(questions)} fixed answers; 3 judges x 3 runs = {len(questions) * 9} judgments. Temperature {args.temperature}.")
    terminal = sys.stdout
    with (directory / "model.log").open("a", encoding="utf-8") as log:
        # Run retrieval in its own process before importing the answer pipeline, so
        # duplicate embedding/reranking models do not remain resident together.
        if not retrieval_complete(directory / "retrieval.json", args.limit):
            print("Evaluating retrieval separately (bypasses the rule-engine shortcut)...", flush=True)
            subprocess.run([sys.executable, "-m", "evaluation.metrics.retrieval_recall", "--limit", str(args.limit),
                            "--out", str(directory / "retrieval.json")], cwd=ROOT, check=True)
        if len(state["responses"]) < len(questions):
            with Progress("Loading answer pipeline", stream=terminal), redirect_stdout(log), redirect_stderr(log):
                from backend.rag import pipeline
                if pipeline.get_collection() is None:
                    raise ValueError("Policy index missing. Review documents and run ./run.sh --index first.")
                rag_info = {"model": pipeline.LLM_MODEL, "embed_model": pipeline.EMBED_MODEL,
                            "collection": pipeline.COLLECTION_NAME, "rerank_top_k": pipeline.RERANK_TOP_K}
                if state["metadata"].get("rag", rag_info) != rag_info:
                    raise ValueError("RAG configuration changed during an incomplete answer-generation run")
                state["metadata"]["rag"] = rag_info
            from evaluation.benchmarks.run_grounding_benchmark import run_questions
            # Reuse the existing runner's evidence fields, but checkpoint the whole
            # experiment after each answer so resume never regenerates saved answers.
            with Progress("Answering", len(questions), stream=terminal) as progress:
                progress.update(len(state["responses"]))
                for number in range(len(state["responses"]), len(questions)):
                    with redirect_stdout(log), redirect_stderr(log):
                        row = run_questions([questions[number]], pipeline.ask, directory / "last_response.json")[0]
                    row["question_id"] = number + 1
                    state["responses"].append(row)
                    checkpoint(directory, state)
                    progress.update(number + 1)
        answers_hash = fingerprint(state["responses"])
        if state["metadata"].get("responses_sha256", answers_hash) != answers_hash:
            raise ValueError("Frozen responses changed since judging began")
        state["metadata"]["responses_sha256"] = answers_hash
        checkpoint(directory, state)
        for model in args.models:
            completed = {(r["question_id"], r["run"]) for r in state["judgments"] if r["model"] == model}
            thinking = "thinking" in model_info[model]["capabilities"] or model.startswith("qwen3:")
            with Progress(f"Judging {model}", len(questions) * REPEATS, stream=terminal) as progress:
                progress.update(len(completed))
                for repeat in range(1, REPEATS + 1):
                    for response in state["responses"]:
                        key = (response["question_id"], repeat)
                        if key in completed:
                            continue
                        with redirect_stdout(log), redirect_stderr(log):
                            result = grade_once(client, model, response, repeat, temperature=args.temperature,
                                                seed=args.seed, thinking=thinking)
                        state["judgments"].append(result)
                        checkpoint(directory, state)
                        completed.add(key)
                        progress.update(len(completed))
    from llm_judge_test.compare_results import compare
    summary = compare(directory)
    return 1 if summary["failed_or_skipped_judgments"] or summary["missing_judgments"] or summary["missing_answers"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__ or "RAG + three local judges, three independent runs each")
    parser.add_argument("--models", nargs=3, default=DEFAULT_MODELS, metavar=("QWEN", "GEMMA", "LLAMA"))
    parser.add_argument("--limit", type=int, default=60, help="first N corrected-key questions (1-60)")
    parser.add_argument("--temperature", type=float, default=0, help="fixed for all calls; default 0")
    parser.add_argument("--seed", type=int, default=42, help="same recorded seed on every independent call")
    parser.add_argument("--timeout", type=float, default=120, help="timeout in seconds per judge call")
    parser.add_argument("--output-dir", type=Path, help="new directory; defaults to llm_judge_test/results/<timestamp>")
    parser.add_argument("--resume", type=Path, help="resume an existing experiment; do not regenerate completed judgments")
    parser.add_argument("--responses", type=Path, help="reuse a saved responses.json matching this corrected key")
    parser.add_argument("--check", action="store_true", help="check the three local models without running the experiment")
    args = parser.parse_args()
    if not 1 <= args.limit <= 60 or len(set(args.models)) != 3:
        parser.error("Use 1-60 questions and three distinct model tags")
    if not math.isfinite(args.temperature) or args.temperature < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Temperature must be finite/nonnegative and timeout finite/positive")
    if args.resume and (args.responses or args.output_dir):
        parser.error("--resume cannot be combined with --responses or --output-dir")
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nStopped. Completed answers/judgments were checkpointed; resume with the same settings.")
        return 130
    except Exception as error:
        print(f"Experiment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
