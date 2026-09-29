# run with: python -m pytest rules/test_engine.py -v

import pytest

from rules import EquipmentItem, PurchaseRequest, RuleEngine, parse_query, should_use_rule_engine
from rules import form_router as F

engine = RuleEngine()


def ev(**kw):
    return engine.evaluate(PurchaseRequest(**kw))


# the 18 main scenarios

def test_01_50k_non_federal():
    r = ev(amount=50_000)
    assert r.competitive_bid_required is False
    assert r.sspr_required is False


def test_02_100k_non_federal():
    r = ev(amount=100_000)
    assert r.competitive_bid_required is True
    assert r.sspr_required is True
    assert r.sspr_sections == ["I", "VII", "VIII"]


def test_03_20k_federal_contract():
    r = ev(amount=20_000, funding="federal_contract")
    assert r.competitive_bid_required is False
    assert r.sspr_required is True
    assert r.sspr_sections == ["I", "II", "VII", "VIII"]   # competitive proposals (3 quotes)
    assert F.FAR_FLOWDOWNS in r.form_names


def test_04_40k_federal_grant():
    r = ev(amount=40_000, funding="federal_grant")
    assert r.competitive_bid_required is False
    assert r.sspr_required is False


def test_05_60k_federal_grant():
    r = ev(amount=60_000, funding="federal_grant")
    assert r.competitive_bid_required is False
    assert r.sspr_required is True


def test_06_150k_federal_grant():
    r = ev(amount=150_000, funding="federal_grant")
    assert r.competitive_bid_required is True
    assert r.sspr_required is True
    assert F.ANTI_LOBBYING in r.form_names


def test_07_mixed_9k_federal_state_rules_only():
    r = ev(amount=100_000, funding="federal_grant", federal_amount=9_000)
    assert r.federal_rules_apply is False
    assert r.funding.is_mixed
    assert r.competitive_bid_required is True          # state rules, still $100K
    assert F.FEDERAL_FUNDS_CHECKLIST not in r.form_names


def test_08_mixed_11k_federal_whole_transaction():
    r = ev(amount=100_000, funding="federal_grant", federal_amount=11_000)
    assert r.federal_rules_apply is True
    assert "ENTIRE" in r.funding.explanation
    assert F.FEDERAL_FUNDS_CHECKLIST in r.form_names
    assert F.DEBARMENT in r.form_names


def test_09_200k_small_business_no_bid():
    r = ev(amount=200_000, source_selection="small_business")
    assert r.competitive_bid_required is False
    assert r.sspr_required is True
    assert r.sspr_sections == ["I", "III", "VII", "VIII"]
    assert r.thresholds.small_business_quotes == 2


def test_10_300k_small_business_bid_required():
    r = ev(amount=300_000, source_selection="small_business")
    assert r.competitive_bid_required is True
    assert r.has_flag("SB_LIMIT_EXCEEDED")


def test_11_split_order_60k_55k():
    r = ev(amount=60_000, related_orders=[55_000])
    assert r.has_flag("SPLIT_ORDER")
    assert r.thresholds.evaluated_value == 115_000
    assert r.competitive_bid_required is True


def test_12_multi_year_federal_grant():
    r = ev(amount=125_000, funding="federal_grant", contract_years=5)
    assert r.competitive_bid_required is True
    assert r.sspr_required is True


def test_12b_multi_year_non_federal_uses_annual_value():
    r = ev(amount=125_000, contract_years=5)
    assert r.thresholds.evaluated_value == 25_000
    assert r.competitive_bid_required is False


def test_13_175k_federal_grant_sole_source():
    r = ev(amount=175_000, funding="federal_grant", source_selection="sole_source",
           sole_source_justification="one_of_a_kind")
    assert r.competitive_bid_required is False
    assert r.sspr_required is True
    assert r.sspr_sections == ["I", "III", "IV", "VII", "VIII"]


def test_14_150k_janitorial():
    r = ev(amount=150_000, description="janitorial services for the new science building")
    cs = r.categories.covered_service
    assert cs is not None and "janitorial" in cs.services
    assert cs.afscme_notice_required is True
    assert cs.wage_parity_required is True


def test_15_80k_security_services():
    r = ev(amount=80_000, description="security guard services for the stadium")
    cs = r.categories.covered_service
    assert cs is not None and "security" in cs.services
    assert cs.afscme_notice_required is False
    assert cs.wage_parity_required is False


def test_16_200k_it_consulting_not_covered():
    r = ev(amount=200_000, description="IT consulting for a data security assessment")
    assert r.categories.covered_service is None


def test_17_federal_grant_data_it_seven_forms():
    r = ev(amount=120_000, funding="federal_grant", vendor_accesses_data=True, it_services=True,
           description="cloud software platform")
    assert set(r.form_names) == {F.SSPR, F.FEDERAL_FUNDS_CHECKLIST, F.ANTI_LOBBYING, F.DEBARMENT,
                                 F.DATA_SECURITY_APPENDIX, F.IS3, F.UG_FLOWDOWNS}
    assert len(r.forms) == 7


def test_18_equipment_tagging():
    r = ev(items=[EquipmentItem("centrifuge", 4_800), EquipmentItem("microscope", 5_200)])
    tagged = {e.item.name: e.must_tag for e in r.categories.equipment}
    assert tagged == {"centrifuge": False, "microscope": True}


# boundary cases

@pytest.mark.parametrize("cost,tag", [(4_999, False), (5_000, True), (5_001, True)])
def test_equipment_boundary(cost, tag):
    assert ev(items=[("x", cost)]).categories.equipment[0].must_tag is tag


def test_equipment_pre_2004_threshold():
    r = ev(items=[EquipmentItem("old scope", 2_000, acquired_before_july_2004=True)])
    assert r.categories.equipment[0].must_tag is True


@pytest.mark.parametrize("amount,funding,sspr", [
    (49_999, "federal_grant", False), (50_000, "federal_grant", True),
    (14_999, "federal_contract", False), (15_000, "federal_contract", True),
    (99_999, "non_federal", False), (100_000, "non_federal", True),
])
def test_sspr_boundaries(amount, funding, sspr):
    assert ev(amount=amount, funding=funding).sspr_required is sspr


@pytest.mark.parametrize("fed,federal_rules", [(10_000, False), (10_001, True)])
def test_mixed_funding_boundary(fed, federal_rules):
    assert ev(amount=100_000, funding="federal_grant", federal_amount=fed).federal_rules_apply is federal_rules


def test_fully_federal_under_10k_still_federal():
    r = ev(amount=8_000, funding="federal_grant")
    assert r.federal_rules_apply is True
    assert F.DEBARMENT in r.form_names


# sole source

@pytest.mark.parametrize("just", ["pre_work", "price", "brand", "familiarity"])
def test_disallowed_sole_source_requires_bid(just):
    r = ev(amount=150_000, funding="federal_grant", source_selection="sole_source",
           sole_source_justification=just)
    assert r.has_flag("SOLE_SOURCE_INVALID")
    assert r.competitive_bid_required is True


def test_geographic_only_disallowed_for_federal():
    fed = ev(amount=150_000, funding="federal_grant", source_selection="sole_source",
             sole_source_justification="geographic")
    assert fed.has_flag("SOLE_SOURCE_INVALID")


def test_no_competition_only_for_grants():
    r = ev(amount=150_000, funding="federal_contract", source_selection="sole_source",
           sole_source_justification="no_competition")
    assert r.has_flag("SOLE_SOURCE_INVALID")


def test_non_federal_sole_source_sections():
    r = ev(amount=150_000, source_selection="sole_source", sole_source_justification="match_existing")
    assert r.sspr_sections == ["I", "III", "IV", "V", "VI", "VII", "VIII"]


def test_certified_cost_pricing():
    r = ev(amount=3_000_000, funding="federal_contract", source_selection="sole_source",
           sole_source_justification="one_of_a_kind", commercial_item=False)
    assert F.CERTIFIED_COST_PRICING in r.form_names
    commercial = ev(amount=3_000_000, funding="federal_contract", source_selection="sole_source",
                    sole_source_justification="one_of_a_kind", commercial_item=True)
    assert F.CERTIFIED_COST_PRICING not in commercial.form_names


def test_professional_services_not_allowed_with_federal():
    r = ev(amount=150_000, funding="federal_grant", source_selection="professional_services")
    assert r.has_flag("SELECTION_NOT_ALLOWED")
    assert r.competitive_bid_required is True


def test_urgent_non_federal_exempt():
    r = ev(amount=150_000, source_selection="urgent")
    assert r.competitive_bid_required is False
    assert r.sspr_sections == ["I", "VI", "VII", "VIII"]


# contracting out

def test_covered_service_displacement_prohibited():
    r = ev(amount=50_000, description="janitorial service contract", displaces_uc_employees=True)
    assert r.categories.covered_service.prohibited is True
    assert any(f.code == "COVERED_SERVICE" and f.severity == "block" for f in r.flags)


def test_covered_service_short_term_no_parity():
    r = ev(amount=150_000, description="custodial services", duration_days=60)
    cs = r.categories.covered_service
    assert cs.afscme_notice_required and not cs.wage_parity_required


def test_skilled_craft_building_maintenance_not_covered():
    assert ev(amount=50_000, description="building maintenance - HVAC repair").categories.covered_service is None


def test_phi_requires_baa_deidentified_does_not():
    assert F.BAA in ev(amount=50_000, description="vendor will access protected health information").form_names
    assert F.BAA not in ev(amount=1_000, description="vendor receives only de-identified health information").form_names


def test_prompt_context_format():
    ctx = ev(amount=175_000, funding="federal_grant", source_selection="sole_source").to_prompt_context()
    assert ctx.startswith("=== RULE ENGINE DETERMINATION (authoritative")
    assert "Competitive bid required: NO" in ctx
    assert "SSPR form required: YES" in ctx
    assert ctx.rstrip().endswith("=== END RULE ENGINE DETERMINATION ===")


def test_answer_header_mixed_funding_state_only():
    h = ev(amount=15_000, funding="federal_grant", federal_amount=9_500).to_answer_header()
    assert "do NOT apply" in h and "$9,500" in h and "SSPR required: NO" in h


def test_answer_header_equipment_and_covered_service():
    h = ev(items=[("centrifuge", 4_800), ("microscope", 5_200)]).to_answer_header()
    assert "centrifuge ($4,800): no tagging required" in h and "microscope ($5,200): must be tagged" in h
    h = ev(amount=50_000, description="janitorial", displaces_uc_employees=True).to_answer_header()
    assert "PROHIBITED" in h


# parsing actual questions (mostly worded like the benchmark ones)

def q(text):
    return engine.evaluate_query(text)


def test_nl_equipment_q32():
    r = q("I'm a lab manager purchasing a centrifuge for $4,800 and a microscope for $5,200. "
          "Do I need to have either or both tagged and tracked in the asset management system?")
    tagged = {e.item.name: e.must_tag for e in r.categories.equipment}
    assert tagged == {"centrifuge": False, "microscope": True}


def test_nl_janitorial_displacement_q41():
    r = q("Our department wants to contract out a $50,000 janitorial service contract for a new building. "
          "We currently have three UC janitorial staff who clean adjacent buildings. If this contract would "
          "eliminate their jobs, is it allowed?")
    assert r.categories.covered_service.prohibited is True
    assert r.categories.covered_service.afscme_notice_required is False


def test_nl_mixed_funding_q14():
    r = q("I'm purchasing a $25,000 piece of lab equipment. I plan to pay $12,000 from my federal NIH grant "
          "and $13,000 from departmental discretionary funds. Can the $13,000 portion just follow UC standard "
          "procurement rules since it's not federal money?")
    assert r.funding.federal_amount == 12_000 and r.funding.total == 25_000
    assert r.federal_rules_apply is True


def test_nl_mixed_funding_q15():
    r = q("I have a $15,000 purchase where I'm using $9,500 from a federal NSF grant and $5,500 from a state "
          "fund. Since the federal portion is under $10,000, can I avoid applying federal procurement rules?")
    assert r.funding.federal_amount == 9_500
    assert r.federal_rules_apply is False


def test_nl_related_orders_q9():
    r = q("I have a federal grant and need to buy two separate pieces of equipment from the same vendor - one "
          "for $30,000 and another for $28,000. They are for related experiments in the same project. Since "
          "each individual purchase is under $50,000, do I still need to submit an SSPR form?")
    assert r.has_flag("SPLIT_ORDER")
    assert r.sspr_required is True


def test_nl_multi_year():
    r = q("We have a 5-year service contract at $25K per year paid from an NSF grant. Do we need to bid it?")
    assert r.thresholds.evaluated_value == 125_000
    assert r.competitive_bid_required is True


def test_nl_split_intent_under_threshold_q11():
    r = q("I need to buy $60,000 worth of lab equipment from the same vendor. The competitive bid threshold is "
          "$50,000. My colleague suggested I place two separate purchase orders - one for $35,000 and another "
          "for $25,000 - so we can process them faster without going through the formal bid process.")
    assert r.has_flag("SPLIT_ORDER")
    assert r.thresholds.evaluated_value == 60_000


def test_nl_annual_aggregate_q2():
    r = q("I expect to place multiple orders throughout the fiscal year from a single vendor totaling "
          "approximately $125,000. Each individual order will be under $20,000. Do I need competitive bidding?")
    assert r.competitive_bid_required is True
    assert r.has_flag("SPLIT_ORDER")


def test_nl_small_business_q5():
    r = q("I need to purchase $185,000 worth of specialized lab furniture from a certified small business "
          "vendor. Can I use the small business set-aside exception?")
    assert r.competitive_bid_required is False
    assert r.thresholds.small_business_quotes == 2


def test_nl_insurance_limit_is_not_a_purchase_amount():
    p = parse_query("I'm hiring a caterer for our department event. The vendor has a general liability policy "
                    "with a $500,000 per occurrence limit. Can I proceed?")
    assert not p.has_purchase


def test_nl_umbrella_policy_amount_is_not_purchase():
    p = parse_query("A vendor we want to contract with argues that their general liability insurance is only "
                    "$500,000 per occurrence, but they have a $2 million umbrella policy that kicks in after the "
                    "$500,000 is exhausted. Does this satisfy the $1 million per occurrence requirement?")
    assert not p.has_purchase


def test_nl_alcohol_inventory_is_not_equipment_tagging():
    p = parse_query("Our lab needs to purchase 200-proof ethanol tax-free at a cost of $1,200. I have a DEA "
                    "registration but haven't done an inventory count since last year.")
    assert p.request.items == []


def test_nl_donated_equipment_threshold():
    r = q("We received a donated piece of equipment with a market value of $5,500 but we paid $0 for it. "
          "Does the $5,000 threshold apply to donated equipment?")
    assert [e.must_tag for e in r.categories.equipment] == [True]


def test_nl_grant_size_is_not_purchase_amount():
    p = parse_query("I am a PI on a $500,000 grant. I need to purchase specialized software that costs $12,000.")
    assert p.request.amount == 12_000


def test_nl_sole_source_familiarity_rejected():
    r = q("A researcher requests a $120,000 sole source procurement for a specific brand of software because "
          "the team is already proficient in it.")
    assert r.has_flag("SOLE_SOURCE_INVALID")


def test_nl_reference_question_q7():
    r = q("When is an SSPR form required for federal purchases?")
    assert r.thresholds is None
    ctx = r.to_prompt_context()
    assert "$15,000" in ctx and "$50,000" in ctx


@pytest.mark.parametrize("text,expected", [
    ("What is the competitive bidding threshold?", True),
    ("Do I need to tag a $6,000 spectrometer?", True),
    ("Can we contract out custodial services?", True),
    ("What is the duration of the ban on UC contracts for former employees?", False),
    ("Which terms and conditions govern all UC purchase orders?", False),
    ("What two pieces of information must be documented for a business meal expense?", False),
])
def test_should_use_rule_engine(text, expected):
    assert should_use_rule_engine(text) is expected
