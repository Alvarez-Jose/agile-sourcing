# llm_judge_test/compare_results.py
# compare repeated grades within each judge and majority verdicts across judges.
# run: python -m llm_judge_test.compare_results llm_judge_test/results/<run>
import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_judge_test.common import GRADES, SCORES, fingerprint, save_csv, save_json


def majority(grades):
    # A failed/missing call is not a vote, and a partial run is not a completed panel.
    if len(grades) != 3 or any(grade not in GRADES for grade in grades):
        return "INCOMPLETE"
    grade, count = Counter(grades).most_common(1)[0]
    return grade if count >= 2 else "NO_CONSENSUS"


def analyze(state):
    models = state["metadata"]["config"]["models"]
    responses = state["responses"]
    expected_questions = state["metadata"]["config"].get("question_count", len(responses))
    if len(responses) > expected_questions:
        raise ValueError("More responses than configured questions")
    if len(models) != 3 or len(set(models)) != 3:
        raise ValueError("Expected three distinct judges")
    ids = [row["question_id"] for row in responses]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question IDs")
    expected_hash = state["metadata"].get("responses_sha256")
    if expected_hash and expected_hash != fingerprint(responses):
        raise ValueError("Frozen response checksum does not match")
    votes = {}
    for row in state["judgments"]:
        key = (row["question_id"], row["model"], row["run"])
        if key in votes or row["model"] not in models or row["run"] not in (1, 2, 3) or row["question_id"] not in ids:
            raise ValueError(f"Duplicate or invalid judgment key: {key}")
        if row["status"] == "ok" and row.get("grade") not in GRADES:
            raise ValueError(f"Invalid successful grade: {key}")
        votes[key] = row
    rows = []
    model_stats = {model: {"complete_questions": 0, "consistent_questions": 0,
                          "changed_question_ids": [], "majority_counts": Counter()} for model in models}
    for response in responses:
        number = response["question_id"]
        row = {"question_id": number, "question": response["question"],
               "reference_answer": response["ground_truth"], "rag_answer": response["system_answer"]}
        decisions = []
        for index, model in enumerate(models, 1):
            grades = []
            for run in (1, 2, 3):
                vote = votes.get((number, model, run), {})
                grade = vote.get("grade") if vote.get("status") == "ok" else None
                grades.append(grade)
                row[f"model{index}_run{run}"] = grade or "UNAVAILABLE"
            decision = majority(grades)
            decisions.append(decision)
            consistent = len(set(grades)) == 1 if decision != "INCOMPLETE" else None
            row[f"model{index}_majority"] = decision
            row[f"model{index}_score"] = SCORES.get(decision, "")
            row[f"model{index}_consistent"] = "unavailable" if consistent is None else consistent
            stats = model_stats[model]
            stats["majority_counts"][decision] += 1
            if decision != "INCOMPLETE":
                stats["complete_questions"] += 1
                stats["consistent_questions"] += int(consistent)
                if not consistent:
                    stats["changed_question_ids"].append(number)
        eligible = all(grade in GRADES for grade in decisions)
        row["agreement"] = ("ALL_AGREE" if len(set(decisions)) == 1 else "DISAGREE") if eligible else "UNRESOLVED"
        row["panel_verdict"] = majority(decisions) if eligible else "UNRESOLVED"
        row["distinct_majority_grades"] = len(set(decisions)) if eligible else ""
        row["score_spread"] = max(map(SCORES.get, decisions)) - min(map(SCORES.get, decisions)) if eligible else ""
        rows.append(row)
    pairs = []
    for first, second in combinations(range(1, 4), 2):
        eligible = [row for row in rows if row[f"model{first}_majority"] in GRADES and row[f"model{second}_majority"] in GRADES]
        agreed = [row["question_id"] for row in eligible if row[f"model{first}_majority"] == row[f"model{second}_majority"]]
        pairs.append({"models": [models[first - 1], models[second - 1]], "comparable_questions": len(eligible),
                      "agreed": len(agreed), "agreement_rate": len(agreed) / len(eligible) if eligible else None,
                      "disagreed_question_ids": [row["question_id"] for row in eligible if row["question_id"] not in agreed]})
    disagreement = sorted([row for row in rows if row["agreement"] == "DISAGREE"],
                          key=lambda row: (-row["distinct_majority_grades"], -row["score_spread"], row["question_id"]))
    summary = {
        "questions": len(rows), "model_columns": {f"model{i}": model for i, model in enumerate(models, 1)},
        "score_encoding": SCORES, "per_model": model_stats, "pairwise": pairs,
        "all_agree_question_ids": [row["question_id"] for row in rows if row["agreement"] == "ALL_AGREE"],
        "all_agree_by_grade": {grade: [row["question_id"] for row in rows if row["agreement"] == "ALL_AGREE" and
                                      row["model1_majority"] == grade] for grade in GRADES},
        "disagree_question_ids": [row["question_id"] for row in disagreement],
        "unresolved_question_ids": [row["question_id"] for row in rows if row["agreement"] == "UNRESOLVED"],
        "failed_or_skipped_judgments": sum(row["status"] != "ok" for row in state["judgments"]),
        "expected_questions": expected_questions, "missing_answers": expected_questions - len(rows),
        "missing_judgments": expected_questions * 9 - len(votes),
        "note": "Agreement and repeatability do not establish policy correctness. Reference answers are not expert ground truth.",
    }
    return rows, disagreement, summary


def compare(directory):
    directory = Path(directory)
    state = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    rows, disagreement, summary = analyze(state)
    retrieval_path = directory / "retrieval.json"
    if retrieval_path.exists():
        retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
        if len(retrieval) != summary["expected_questions"] or [row["q"] for row in retrieval] != list(range(1, len(retrieval) + 1)):
            raise ValueError("Retrieval results are incomplete or have mismatched question IDs")
        by_id = {row["q"]: row for row in retrieval}
        for row in rows:
            evidence = by_id[row["question_id"]]
            row.update(retrieval_first_hit_rank_top5=evidence.get("first_hit_rank"),
                       retrieval_hit_at_5=evidence["hit_at_5"], retrieval_hit_in_pool=evidence["hit_in_pool"],
                       retrieved_documents=json.dumps(evidence.get("top_docs", []), ensure_ascii=False))
        count = len(retrieval)
        summary["retrieval"] = {"questions": count,
                                "recall_at_1": sum(row.get("first_hit_rank") == 1 for row in retrieval) / count,
                                "recall_at_5": sum(row["hit_at_5"] for row in retrieval) / count,
                                "recall_in_pool": sum(row["hit_in_pool"] for row in retrieval) / count}
    fields = ["question_id", "question", "reference_answer", "rag_answer"]
    for index in (1, 2, 3):
        fields.extend([f"model{index}_run{run}" for run in (1, 2, 3)])
        fields.extend([f"model{index}_majority", f"model{index}_score", f"model{index}_consistent"])
    fields.extend(["agreement", "panel_verdict", "distinct_majority_grades", "score_spread"])
    fields.extend(["retrieval_first_hit_rank_top5", "retrieval_hit_at_5", "retrieval_hit_in_pool", "retrieved_documents"])
    save_csv(directory / "comparison.csv", rows, fields)
    save_csv(directory / "disagreements.csv", disagreement, fields)
    # Compact presentation view, alongside the detailed comparison with all nine grades.
    compact_fields = ["question_id", "question", "reference_answer", "rag_answer",
                      "model1_grade", "model1_score", "model2_grade", "model2_score", "model3_grade", "model3_score", "panel_verdict"]
    compact = [{**row, **{f"model{i}_grade": row[f"model{i}_majority"] for i in (1, 2, 3)}} for row in rows]
    save_csv(directory / "results.csv", compact, compact_fields)
    save_json(directory / "comparison_summary.json", summary)
    print("\nJudge comparison (reference agreement, not expert accuracy)")
    if summary.get("retrieval"):
        retrieval = summary["retrieval"]
        print(f"Expected-document recall: @1 {retrieval['recall_at_1']:.1%}, @5 {retrieval['recall_at_5']:.1%}, "
              f"candidate pool {retrieval['recall_in_pool']:.1%}")
    for model, stats in summary["per_model"].items():
        total = stats["complete_questions"]
        rate = f"{stats['consistent_questions'] / total:.1%}" if total else "unavailable"
        print(f"{model}: identical grades in {stats['consistent_questions']}/{total} complete questions ({rate}); "
              f"changed on {stats['changed_question_ids']}; verdict counts {dict(stats['majority_counts'])}")
    for pair in summary["pairwise"]:
        print(f"{' vs '.join(pair['models'])}: agree on {pair['agreed']}/{pair['comparable_questions']} comparable questions")
    print(f"All three agree: {len(summary['all_agree_question_ids'])}; disagree: {len(summary['disagree_question_ids'])}; "
          f"unresolved: {len(summary['unresolved_question_ids'])}")
    print(f"Strongest disagreement first (more distinct grades, then larger score spread): {summary['disagree_question_ids']}")
    print(f"Failed/skipped calls: {summary['failed_or_skipped_judgments']}; missing calls: {summary['missing_judgments']}; "
          f"missing answers: {summary['missing_answers']}")
    print(f"Reports saved in {directory}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Compare three repeats within and across three judges")
    parser.add_argument("directory", type=Path, help="experiment directory containing experiment.json")
    args = parser.parse_args()
    try:
        summary = compare(args.directory)
        return 1 if summary["missing_judgments"] or summary["failed_or_skipped_judgments"] or summary["missing_answers"] else 0
    except (OSError, ValueError, KeyError) as error:
        print(f"Comparison failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
