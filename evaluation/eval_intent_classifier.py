# evaluation/eval_intent_classifier.py
# compares the new embedding intent classifier (13 intents) against the old logistic
# regression model (6 labels) on intent_eval_set.json. none of those questions are in
# the classifier examples or the benchmark.
#
#   python evaluation/eval_intent_classifier.py
#   python evaluation/eval_intent_classifier.py --threshold 0.35 --verbose

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sentence_transformers import SentenceTransformer

from rag_pipeline.retriever.intent_classifier import INTENT_CATEGORIES, IntentClassifier

TO_COARSE = {
    "bidding_threshold": "competitive_bidding", "split_order": "competitive_bidding",
    "sole_source": "competitive_bidding", "sspr_form": "federal_funds", "federal_funding": "federal_funds",
    "post_employment_coi": "conflict_of_interest", "conflict_of_interest": "conflict_of_interest",
    "contracting_out": "contracts_services", "independent_contractor": "contracts_services",
    "equipment_tagging": "equipment_management", "data_security": "general_policy",
    "risk_insurance": "general_policy", "general": "general_policy",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    items = json.load(open(ROOT / "evaluation/benchmarks/intent_eval_set.json", encoding="utf-8"))["items"]
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    clf = IntentClassifier(embedder, threshold=args.threshold) if args.threshold is not None else IntentClassifier(embedder)

    fine = route = coarse_new = 0
    for it in items:
        r = clf.classify(it["q"])
        fine += r["intent"] == it["intent"]
        route += r["route_to"] == INTENT_CATEGORIES[it["intent"]]["route_to"]
        coarse_new += TO_COARSE[r["intent"]] == it["coarse"]
        if r["intent"] != it["intent"]:
            if args.verbose:
                print(f"  MISS {it['intent']:>22} -> {r['intent']:<22} ({r['confidence']:.2f}) {it['q'][:70]}")

    n = len(items)
    print(f"Embedding classifier (threshold {clf.threshold}):")
    print(f"  13-way intent accuracy: {fine}/{n} = {fine / n:.1%}")
    print(f"  route accuracy:         {route}/{n} = {route / n:.1%}")
    print(f"  coarse (6-label):       {coarse_new}/{n} = {coarse_new / n:.1%}")

    # old logistic regression model, still in models/intent_classifier for comparison
    import pickle
    with open(ROOT / "models/intent_classifier/classifier.pkl", "rb") as f:
        old = pickle.load(f)
    old_preds = old.predict(embedder.encode([it["q"] for it in items]))
    coarse_old = sum(p == it["coarse"] for p, it in zip(old_preds, items))
    print("old LogReg classifier (models/intent_classifier):")
    print(f"  coarse (6-label):       {coarse_old}/{n} = {coarse_old / n:.1%}")


if __name__ == "__main__":
    main()
