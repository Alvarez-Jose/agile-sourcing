# run with: python -m pytest rules/test_provenance.py -v
#
# every rule-engine threshold must have a source record, and every source quote must
# still appear in the current policy file (on its stated page, for PDFs). if a policy is
# replaced and the wording/number changes, this fails instead of the rules going stale.
# files live in data/raw_policies (gitignored); a document that isn't there is skipped.
# POLICY_SOURCE_DIRS (os.pathsep-separated) adds more folders, e.g. one holding the
# official SSPR PDF that the page numbers refer to.

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pytest

from rules import PurchaseRequest, RuleEngine
from rules import category_flags as C
from rules import funding_rules as FR
from rules import thresholds as T
from rules.provenance import DOCUMENTS, SOURCES, TOPIC_SOURCES

RAW = Path(__file__).resolve().parents[1] / "data" / "raw_policies"
DIRS = [RAW] + [Path(p) for p in os.environ.get("POLICY_SOURCE_DIRS", "").split(os.pathsep) if p]


def locate(filename: str):
    return next((d / filename for d in DIRS if (d / filename).exists()), None)

CONSTANTS = {
    "COMPETITIVE_BID_THRESHOLD": T.COMPETITIVE_BID_THRESHOLD,
    "SIMPLIFIED_ACQUISITION_THRESHOLD": T.SIMPLIFIED_ACQUISITION_THRESHOLD,
    "FEDERAL_MICRO_PURCHASE": T.FEDERAL_MICRO_PURCHASE,
    "CAMPUS_GRANT_MICRO_PURCHASE_MAX": T.CAMPUS_GRANT_MICRO_PURCHASE_MAX,
    "SMALL_BUSINESS_LIMIT": T.SMALL_BUSINESS_LIMIT,
    "SMALL_BUSINESS_FEDERAL_SSPR_LIMIT": T.SMALL_BUSINESS_FEDERAL_SSPR_LIMIT,
    "SMALL_BUSINESS_TWO_QUOTES_ABOVE": T.SMALL_BUSINESS_TWO_QUOTES_ABOVE,
    "SSPR_FEDERAL_CONTRACT": T.SSPR_FEDERAL_CONTRACT,
    "SSPR_FEDERAL_GRANT": T.SSPR_FEDERAL_GRANT,
    "SSPR_NON_FEDERAL": T.SSPR_NON_FEDERAL,
    "CERTIFIED_COST_PRICING_THRESHOLD": T.CERTIFIED_COST_PRICING_THRESHOLD,
    "ANTI_LOBBYING_THRESHOLD": T.ANTI_LOBBYING_THRESHOLD,
    "EQUIPMENT_TAG_THRESHOLD": C.EQUIPMENT_TAG_THRESHOLD,
    "EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004": C.EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004,
    "AFSCME_NOTICE_THRESHOLD": C.AFSCME_NOTICE_THRESHOLD,
    "WAGE_PARITY_MIN_DAYS": C.WAGE_PARITY_MIN_DAYS,
}

TYPOGRAPHY = str.maketrans({"‐": "-", "‑": "-", "–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"'})


def norm(text: str) -> str:
    # pypdf splits words across lines ("an\nnually") and spreads letters out, so compare
    # with all whitespace removed. NFKC turns ligatures (ﬀ) back into letters
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY))


@lru_cache(maxsize=None)
def pages(filename: str) -> dict:
    path = locate(filename)
    if filename.lower().endswith(".pdf"):
        import pypdf
        return {i: norm(p.extract_text() or "") for i, p in enumerate(pypdf.PdfReader(path).pages, 1)}
    import docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            parts += [cell.text for cell in row.cells]
    return {None: norm("\n".join(parts))}


CASES = [(key, i, src) for key, srcs in SOURCES.items() for i, src in enumerate(srcs)]


@pytest.mark.parametrize("key,i,src", CASES, ids=[f"{k}[{i}]" for k, i, _ in CASES])
def test_quote_still_in_current_document(key, i, src):
    files = DOCUMENTS[src.document_id]["files"]
    if not files:
        assert DOCUMENTS[src.document_id]["url"], f"{key}: external source needs a URL"
        pytest.skip(f"{key}: external source ({src.document_id}), checked by hand")
    present = [f for f in files if locate(f)]
    if not present:
        pytest.skip(f"{key}: none of {files} in {[str(d) for d in DIRS]}")
    quote = norm(src.quote)
    for f in present:
        text = pages(f)
        if f.lower().endswith(".pdf") and f == files[0] and src.page:
            assert quote in text.get(src.page, ""), f"{key}: quote not found on p.{src.page} of {f}"
        else:
            assert quote in "".join(text.values()), f"{key}: quote not found in {f}"


def test_every_threshold_constant_has_a_source():
    assert set(CONSTANTS) <= set(SOURCES)
    for award in FR.MIXED_FUNDING_FEDERAL_TRIGGERS:
        assert "MIXED_FUNDING_FEDERAL_TRIGGERS" in SOURCES, award


@pytest.mark.parametrize("key", sorted(CONSTANTS))
def test_quote_states_the_constant_value(key):
    value = CONSTANTS[key]
    spelled = {f"{value:,}", f"({value})", f"${value // 1000}k", f"${value // 1000}K"}
    assert any(any(s in src.quote for s in spelled) for src in SOURCES[key]), \
        f"{key}={value:,} does not appear in any of its quotes"


def test_mixed_trigger_values_match_sspr_thresholds():
    assert FR.MIXED_FUNDING_FEDERAL_TRIGGERS == {"contract": T.SSPR_FEDERAL_CONTRACT, "grant": T.SSPR_FEDERAL_GRANT}


def test_topic_sources_point_at_known_constants():
    for keys in TOPIC_SOURCES.values():
        assert set(keys) <= set(SOURCES)


# determinations carry their sources

engine = RuleEngine()


def ev(**kw):
    return engine.evaluate(PurchaseRequest(**kw))


def test_purchase_determination_cites_bid_and_sspr_sources():
    r = ev(amount=175_000, funding="federal_grant", source_selection="sole_source")
    keys = r.source_keys()
    assert {"COMPETITIVE_BID_THRESHOLD", "SSPR_FEDERAL_GRANT", "ANTI_LOBBYING_THRESHOLD"} <= set(keys)
    srcs = r.to_dict()["sources"]
    bid = next(s for s in srcs if s["document_id"] == "bus-43")
    assert bid["page"] == 9 and "$100,000 or more" in bid["quote"] and bid["version"].startswith("Interim")


def test_mixed_funding_cites_sspr_section_i():
    r = ev(amount=100_000, funding="federal_grant", federal_amount=20_000)
    assert "MIXED_FUNDING_FEDERAL_TRIGGERS" in r.source_keys()
    assert any("check Federal side only" in line for line in r.source_lines())


@pytest.mark.parametrize("kw,key", [
    (dict(items=[("microscope", 5_200)]), "EQUIPMENT_TAG_THRESHOLD"),
    (dict(amount=150_000, description="janitorial"), "AFSCME_NOTICE_THRESHOLD"),
    (dict(amount=60_000, related_orders=[55_000]), "SPLIT_ORDER"),
    (dict(amount=200_000, source_selection="small_business"), "SMALL_BUSINESS_TWO_QUOTES_ABOVE"),
])
def test_category_determinations_cite_sources(kw, key):
    assert key in ev(**kw).source_keys()


def test_reference_question_cites_sources():
    r = engine.evaluate_query("When is an SSPR form required for federal purchases?")
    assert {"SSPR_FEDERAL_CONTRACT", "SSPR_FEDERAL_GRANT"} <= set(r.source_keys())
