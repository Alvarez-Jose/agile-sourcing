# run with: python -m pytest rules/test_ladders.py -v

import pytest

from rules import RuleEngine, parse_query, should_use_rule_engine
from rules.policy_ladders import (evaluate_alcohol_permit, evaluate_business_meal, evaluate_ladders,
                                  evaluate_post_employment, evaluate_risk_matrix)
from rules.provenance import SOURCES

engine = RuleEngine()


# post-employment

def test_two_year_ban_when_former_employee_took_part_in_the_decision():
    d = evaluate_post_employment("A former UC employee helped evaluate the bids for this contract last year. "
                                 "Can we award it to her company?")
    assert d.severity == "block" and "two years" in d.headline
    assert "POST_EMPLOYMENT_TWO_YEAR" in d.source_keys


def test_12_month_ban_for_policymaking_role_in_same_department():
    d = evaluate_post_employment("Our former director wants to contract with the same department he left six "
                                 "months ago.")
    assert d.severity == "block" and "12 months" in d.headline


def test_retiree_is_exempt():
    d = evaluate_post_employment("A professor who retired from UC last spring wants to bid on a campus contract.")
    assert d.severity == "require" and "exempt" in d.headline


def test_one_year_rule_is_about_representing_others():
    d = evaluate_post_employment("An ex-employee is now representing a vendor before the campus to influence an "
                                 "award.")
    assert d.severity == "block" and "One-year" in d.headline


def test_no_facts_still_states_the_ladder_and_that_funding_is_irrelevant():
    q = ("A former UC employee was subject to a one-year contract ban. If a UC department wants to hire him "
         "temporarily as an independent contractor for a specialized project that receives no direct UC funding, "
         "does the ban still apply?")
    d = evaluate_post_employment(q)
    assert d.severity == "require"
    assert "funding source is irrelevant" in d.headline
    assert "12 MONTHS" in d.lines[0] and "TWO YEARS" in d.lines[0]


def test_not_triggered_without_a_former_employee():
    assert evaluate_post_employment("Can I accept a gift from a supplier?") is None


def test_not_triggered_outside_a_contracting_context():
    # benchmark Q36: a retiring PI in a tax-free alcohol question is not a post-employment question
    assert evaluate_post_employment("The DEA registration is under a principal investigator who is "
                                    "retiring next month. Can we still use the tax-free permit?") is None


# business meals

def test_business_meal_documentation_checklist():
    d = evaluate_business_meal("What two specific pieces of information must be documented for a business meal "
                               "expense?")
    assert d.severity == "require"
    for item in ("type of expense", "guest list", "name, title", "purpose", "$75"):
        assert item in d.headline
    assert {"BUS79_GUEST_LIST", "BUS79_PURPOSE"} <= set(d.source_keys)


def test_catering_counts_as_a_business_meal():
    assert evaluate_business_meal("I'm hiring a caterer for our department event.") is not None


def test_caterer_insurance_question_is_not_a_documentation_question():
    # benchmark Q38
    assert evaluate_business_meal("I'm hiring a caterer for our department event. The vendor has a general "
                                  "liability policy with a $500,000 per occurrence limit. Can I proceed?") is None


# tax-free alcohol

def test_alcohol_permit_requirements():
    d = evaluate_alcohol_permit("What are the two key requirements for obtaining a tax-free alcohol permit at UC?")
    assert d.severity == "require"
    assert "TTB" in d.headline and "The Regents" in d.headline and "semiannual" in d.headline
    assert "DEA" not in d.headline
    assert "ALCOHOL_SEMIANNUAL_INVENTORY" in d.source_keys


def test_alcohol_scenario_with_dea_and_overdue_inventory():
    d = evaluate_alcohol_permit("Our lab needs 500 mL of 200-proof ethanol tax-free for $1,200. I have a DEA "
                                "registration but haven't done an inventory count since last year. Can I proceed?")
    joined = " ".join(d.conditions)
    assert "DEA registration is not the credential" in joined
    assert "semiannual, not annual" in joined


def test_alcohol_permit_survives_a_retiring_pi():
    d = evaluate_alcohol_permit("The DEA registration is under a principal investigator who is retiring next "
                                "month; we have the annual inventory scheduled for next week. Can we still use the "
                                "tax-free permit for a $50 classroom order?")
    assert any("retirement or departure does not invalidate" in c for c in d.conditions)
    joined = " ".join(d.conditions)
    assert "upcoming scheduled inventory does not block" in joined and "overdue" not in joined


# BUS-63 risk matrix

@pytest.mark.parametrize("text,exposure", [
    ("Do we need a certificate of insurance from a contractor doing building construction?", "D. Physical"),
    ("Vendor will transport students by shuttle to the field site; what insurance do we need?", "K. Transportation"),
    ("The vendor will handle cash at the ticket booth. Is a COI required?", "J. Financial"),
    ("Architectural services for the new lab - COI?", "E. Professional"),
    ("A summer camp for minors run by an outside company - what does the risk matrix say?", "H. Students"),
])
def test_high_risk_exposures_require_a_coi(text, exposure):
    d = evaluate_risk_matrix(text)
    assert d is not None and d.severity == "require"
    assert exposure in d.headline and "must be collected" in d.headline
    assert "RISK_MATRIX_HIGH_COI" in d.source_keys


def test_moderate_digital_risk_does_not_collect_a_coi():
    d = evaluate_risk_matrix("SaaS vendor with access to P2 data only; do we collect a certificate of insurance?")
    assert "Moderate risk" in d.headline and "does not need to be collected" in d.headline


def test_low_digital_risk_does_not_collect_a_coi():
    d = evaluate_risk_matrix("Vendor only sees P1 public data. COI needed?")
    assert "Low risk" in d.headline


def test_general_liability_minimum_question_is_left_to_rag():
    # the matrix says nothing about dollar limits (those are in the T&Cs), so a plain insurance
    # minimum question must not get a matrix determination
    assert evaluate_risk_matrix("What is the minimum general liability insurance a vendor must carry per "
                                "occurrence?") is None


# wiring

@pytest.mark.parametrize("question,code", [
    ("What is the duration of the ban on UC contracts for former employees?", "POST_EMPLOYMENT"),
    ("What two pieces of information must be documented for a business meal expense?", "BUSINESS_MEAL_DOCS"),
    ("What are the two key requirements for obtaining a tax-free alcohol permit at UC?", "ALCOHOL_PERMIT"),
    ("Do we need a certificate of insurance for a vendor transporting students?", "RISK_MATRIX_COI"),
])
def test_engine_runs_the_ladder_and_cites_it(question, code):
    parsed = parse_query(question)
    assert should_use_rule_engine(question, parsed)
    r = engine.evaluate(parsed.request, topics=parsed.topics)
    assert [l.code for l in r.ladders] == [code]
    assert r.is_substantive
    assert r.ladders[0].headline in r.to_answer_header()
    assert set(r.ladders[0].source_keys) <= set(r.source_keys())
    assert r.sources, "ladder determination must carry provenance"


def test_every_ladder_source_key_exists():
    from rules import policy_ladders as L
    texts = ["former employee negotiated the contract", "business meal", "tax-free alcohol permit",
             "certificate of insurance for construction"]
    for text in texts:
        for d in evaluate_ladders(text):
            assert set(d.source_keys) <= set(SOURCES), d.code


def test_threshold_questions_are_untouched():
    r = engine.evaluate_query("Do I need to bid a $150K NIH-funded purchase?")
    assert r.ladders == []
    assert r.competitive_bid_required is True
