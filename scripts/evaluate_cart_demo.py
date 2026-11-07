"""Run synthetic cart-to-SSPR regression cases, not a Qwen accuracy benchmark.

Run: python -m scripts.evaluate_cart_demo
"""
import argparse
import csv
from pathlib import Path

from backend.api.cart_routes import CartRequest, guide, reviewed_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/cart_demo_results.csv"))
    args = parser.parse_args()
    sources = reviewed_sources()
    # Explicit synthetic values exercise each boundary in the reviewed form.
    cases = [
        ("small_cart", "non_federal", "33.24", "3.24", "0", "0", "checked", False),
        ("non_federal_below", "non_federal", "99999.99", "0", "0", "0", "checked", False),
        ("non_federal_at", "non_federal", "100000", "0", "0", "0", "checked", True),
        ("federal_contract_below", "federal_contract", "14999.99", "0", "0", "0", "checked", False),
        ("federal_contract_tax_reaches", "federal_contract", "14900", "100", "0", "0", "checked", True),
        ("federal_grant_at", "federal_grant", "50000", "0", "0", "0", "checked", True),
        ("funding_unknown", "unknown", "33.24", "3.24", "0", "0", "needs_details", None),
        ("shipping_unknown", "non_federal", "33.24", "3.24", None, "0", "needs_details", None),
    ]
    rows = []
    for name, funding, subtotal, tax, shipping, handling, status, required in cases:
        cart = CartRequest(items=[{"description": "Synthetic demo item", "supplier": "Fictional supplier",
                                  "quantity": "1", "unit_price": subtotal, "line_total": subtotal}],
                           currency="USD", subtotal=subtotal, tax=tax, shipping=shipping, handling=handling,
                           funding=funding, reviewed=True, single_purchase=True)
        result = guide(cart, sources)
        passed = result["status"] == status and result.get("sspr_required_by_threshold") == required
        rows.append({"case": name, "funding": funding, "subtotal": subtotal, "tax": tax,
                     "shipping": "unknown" if shipping is None else shipping,
                     "expected_status": status, "actual_status": result["status"],
                     "expected_sspr_required": required, "actual_sspr_required": result.get("sspr_required_by_threshold"),
                     "passed": passed, "llm_called": result["llm_called"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{sum(r['passed'] for r in rows)}/{len(rows)} synthetic cart checks passed. Report: {args.output}")
    print("Source-backed deterministic workflow only; not live CruzBuy, Qwen, or procurement-approval accuracy.")
    if not all(r["passed"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
