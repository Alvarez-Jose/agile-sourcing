"""Controlled natural-language robustness benchmark for Agile Sourcing.

Run from repository root:
  python evaluation/test_robustness.py --mode rules
  python evaluation/test_robustness.py --mode pipeline

No procurement-buyer ground truth is claimed. Expected labels are independently
specified for a narrow, documented set of threshold scenarios. The rules mode
checks the NL parser and deterministic engine; pipeline mode checks routing and
structured determination returned by ask(). The main Answer decision is also checked conservatively (see explanation_consistency.py).
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.explanation_consistency import check_explanation

CASES = [
    # Wording invariance: three equivalent ways to describe one purchase.
    ("bid_120k", "paraphrase", "Does a $120,000 campus-funded purchase require competitive bidding?", 120000, "non_federal", True, True),
    ("bid_120k", "paraphrase", "For a $120,000 non-federal purchase, do I need competitive bids?", 120000, "non_federal", True, True),
    ("bid_120k", "paraphrase", "We're purchasing $120,000 in lab supplies using campus funds. Is competitive bidding required?", 120000, "non_federal", True, True),
    ("bid_80k", "paraphrase", "Does a $80,000 campus-funded purchase require competitive bidding?", 80000, "non_federal", False, False),
    ("bid_80k", "paraphrase", "For an $80,000 non-federal purchase, do I need competitive bids?", 80000, "non_federal", False, False),
    ("bid_80k", "paraphrase", "We're purchasing $80,000 in lab supplies using campus funds. Is competitive bidding required?", 80000, "non_federal", False, False),
    # Boundary sensitivity: exact values should flip at the stated threshold.
    ("bid_boundary", "boundary", "Does a non-federal purchase of $99,999 require competitive bidding?", 99999, "non_federal", False, False),
    ("bid_boundary", "boundary", "Does a non-federal purchase of $100,000 require competitive bidding?", 100000, "non_federal", True, True),
    ("bid_boundary", "boundary", "Does a non-federal purchase of $100,001 require competitive bidding?", 100001, "non_federal", True, True),
    # Funding sensitivity: grant and contract SSPR thresholds are different.
    ("grant_sspr", "boundary", "For a $49,999 purchase paid entirely by a federal grant, is an SSPR form required?", 49999, "federal_grant", False, False),
    ("grant_sspr", "boundary", "For a $50,000 purchase paid entirely by a federal grant, is an SSPR form required?", 50000, "federal_grant", False, True),
    ("grant_sspr", "boundary", "For a $50,001 purchase paid entirely by a federal grant, is an SSPR form required?", 50001, "federal_grant", False, True),
    ("contract_sspr", "boundary", "For a $14,999 purchase paid entirely by a federal contract, is an SSPR form required?", 14999, "federal_contract", False, False),
    ("contract_sspr", "boundary", "For a $15,000 purchase paid entirely by a federal contract, is an SSPR form required?", 15000, "federal_contract", False, True),
    ("contract_sspr", "boundary", "For a $15,001 purchase paid entirely by a federal contract, is an SSPR form required?", 15001, "federal_contract", False, True),
    ("funding_switch", "funding", "For a $60,000 purchase using non-federal campus funds, is an SSPR form required?", 60000, "non_federal", False, False),
    ("funding_switch", "funding", "For a $60,000 purchase paid entirely by a federal grant, is an SSPR form required?", 60000, "federal_grant", False, True),
    ("funding_switch", "funding", "For a $60,000 purchase paid entirely by a federal contract, is an SSPR form required?", 60000, "federal_contract", False, True),
]

# A result is independently judged against the manually specified expected
# amounts, funding type and determinations. Tests must not derive these expected
# labels by running the same engine under evaluation.
FIELDS = ("amount", "funding", "bid", "sspr")
CSV_FIELDS = ("id", "group", "kind", "question", "status", "reason",
              "expected_amount", "actual_amount", "expected_funding", "actual_funding",
              "expected_bid", "actual_bid", "expected_sspr", "actual_sspr",
              "intent", "refused", "llm_called", "answer_excerpt",
              "explanation_target", "explanation_status", "explanation_detected", "explanation_reason")


def extract_determination(text):
    """Read only explicit structured yes/no fields, never guess from prose."""
    if not text:
        return {"bid": None, "sspr": None}
    patterns = {
        "bid": r"\bCompetitive bid required:\s*(YES|NO)\b",
        "sspr": r"\bSSPR (?:form )?required:\s*(YES|NO)\b",
    }
    out = {}
    for key, pattern in patterns.items():
        hits = set(re.findall(pattern, str(text), re.I))
        out[key] = (next(iter(hits)).upper() == "YES") if len(hits) == 1 else None
    return out


def assess(expected, actual):
    mismatches = []
    for key in FIELDS:
        value = actual.get(key)
        if value is None:
            mismatches.append(f"{key}:unavailable")
        elif value != expected[key]:
            mismatches.append(f"{key}:expected={expected[key]!r},actual={value!r}")
    return ("PASS" if not mismatches else "FAIL", "; ".join(mismatches))


def run_case(case, mode, ask=None):
    group, kind, question, amount, funding, bid, sspr = case
    expected = dict(amount=amount, funding=funding, bid=bid, sspr=sspr)
    row = dict(id=f"{group}_{CASES.index(case)+1:02}", group=group, kind=kind, question=question,
               expected_amount=amount, expected_funding=funding, expected_bid=bid, expected_sspr=sspr,
               actual_amount=None, actual_funding=None, actual_bid=None, actual_sspr=None,
               intent="", refused="", llm_called="", answer_excerpt="",
               explanation_target="", explanation_status="NOT_RUN",
               explanation_detected="", explanation_reason="")
    try:
        from rules import RuleEngine, parse_query
        parsed = parse_query(question)
        req = parsed.request
        if req is None:
            raise ValueError("Natural-language parser did not return a purchase request")
        actual = dict(amount=req.amount, funding=req.funding, bid=None, sspr=None)
        if mode == "rules":
            result = RuleEngine().evaluate(req, topics=parsed.topics)
            actual.update(bid=result.competitive_bid_required, sspr=result.sspr_required)
        else:
            response = ask(question)
            row.update(intent=response.get("intent", ""), refused=response.get("refused", ""),
                       llm_called=response.get("llm_called", ""),
                       answer_excerpt=str(response.get("answer", ""))[:240])
            # Compare generated Answer, not the fixed Rule/Source block.
            target = "bid" if "competitive bid" in question.lower() or "competitive bidding" in question.lower() else "sspr"
            explanation = check_explanation(
                response.get("answer"), target, expected[target],
                refused=response.get("refused", False),
                llm_called=response.get("llm_called"),
            )
            row.update(explanation_target=target, explanation_status=explanation["status"],
                       explanation_detected=explanation["detected"],
                       explanation_reason=explanation["reason"])
            # This field comes from actual API routing, so if rules didn't run,
            # report unavailable instead of silently substituting the oracle.
            actual.update(extract_determination(response.get("determination")))
            if response.get("refused"):
                row["reason"] = "backend refused"
        status, reason = assess(expected, actual)
        row.update(status=status, reason=(row.get("reason", "") + "; " + reason).strip("; "))
        row.update(actual_amount=actual["amount"], actual_funding=actual["funding"],
                   actual_bid=actual["bid"], actual_sspr=actual["sspr"])
    except Exception as e:
        row.update(status="ERROR", reason=f"{type(e).__name__}: {e}")
    return row


def summarize(rows, mode):
    counts = Counter(r["status"] for r in rows)
    by_kind = {}
    for kind in sorted(set(r["kind"] for r in rows)):
        subset = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = dict(total=len(subset), passed=sum(r["status"] == "PASS" for r in subset),
                             failed=sum(r["status"] == "FAIL" for r in subset),
                             errors=sum(r["status"] == "ERROR" for r in subset))
    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)
    group_summary = {g: {"all_pass": all(r["status"] == "PASS" for r in part),
                         "passing_cases": sum(r["status"] == "PASS" for r in part),
                         "total_cases": len(part)} for g, part in by_group.items()}
    explanation = Counter(r.get("explanation_status", "NOT_RUN") for r in rows)
    return dict(mode=mode, total=len(rows), passed=counts["PASS"], failed=counts["FAIL"],
                errors=counts["ERROR"], pass_rate=(round(counts["PASS"] / len(rows), 4) if rows else None),
                by_kind=by_kind, by_group=group_summary,
                explanation_consistency={"passed": explanation["PASS"],
                                         "contradictions": explanation["CONTRADICTION"],
                                         "manual_review": explanation["REVIEW"],
                                         "not_run": explanation["NOT_RUN"]},
                caveat="Synthetic, developer-labeled checks for parser/rule application; not buyer-validated compliance accuracy or full-answer correctness.")


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--mode", choices=("rules", "pipeline"), default="rules")
    cli.add_argument("--limit", type=int, default=len(CASES))
    cli.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "results" / "robustness")
    args = cli.parse_args(argv)
    if not 1 <= args.limit <= len(CASES):
        cli.error(f"--limit must be between 1 and {len(CASES)}")
    ask = None
    if args.mode == "pipeline":
        # Don't load model and Chroma dependencies for fast rules-only runs.
        from backend.rag.pipeline import ask
        from backend.rag.pipeline import get_collection
        if get_collection() is None:
            cli.error("Policy ChromaDB collection missing; run policy ingestion first")
    rows = [run_case(c, args.mode, ask) for c in CASES[:args.limit]]
    summary = summarize(rows, args.mode)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_file = args.output_dir / f"{args.mode}_results.csv"
    json_file = args.output_dir / f"{args.mode}_summary.json"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    json_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Mode: {args.mode} | PASS {summary['passed']}/{summary['total']} | FAIL {summary['failed']} | ERROR {summary['errors']}")
    print(f"CSV: {csv_file}\nSummary: {json_file}")
    if args.mode == "pipeline":
        e = summary["explanation_consistency"]
        print(f"Answer consistency: PASS {e['passed']} | CONTRADICTION {e['contradictions']} "
              f"| REVIEW {e['manual_review']} | NOT_RUN {e['not_run']}")
        for row in rows:
            if row["explanation_status"] in ("CONTRADICTION", "REVIEW"):
                print(f"  [ANSWER {row['explanation_status']}] {row['id']}: {row['explanation_reason']}")
    for row in rows:
        if row["status"] != "PASS":
            print(f"  [{row['status']}] {row['id']}: {row['reason']}")
    # Review flags do not automatically fail CI, but confirmed contradictions do.
    contradictions = summary["explanation_consistency"]["contradictions"] if args.mode == "pipeline" else 0
    return 0 if summary["failed"] == summary["errors"] == contradictions == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
