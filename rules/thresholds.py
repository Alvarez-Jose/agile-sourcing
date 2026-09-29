# rules/thresholds.py
# dollar thresholds - competitive bid, SSPR, sole source, split orders
#
# numbers come from:
#   BUS-43 (bid threshold, small business program, split orders)
#   CA Public Contract Code 10507 / 10508.5
#   SSPR form rev 12-2025 + the SSPR FAQ (V 4.2021)
#   FAR 15.403-4 for certified cost/pricing data

from dataclasses import dataclass, field
from typing import Optional

from rules.funding_rules import FundingDetermination
from rules.models import Flag, PurchaseRequest

# competitive bidding
COMPETITIVE_BID_THRESHOLD        = 100_000   # BUS-43 + CA PCC. federal is $100K too since CA PCC is stricter than the $250K SAT
SIMPLIFIED_ACQUISITION_THRESHOLD = 250_000   # federal SAT
FEDERAL_MICRO_PURCHASE           = 10_000
CAMPUS_GRANT_MICRO_PURCHASE_MAX  = 50_000    # OMB lets campuses go up to this for grants/coops
SMALL_BUSINESS_LIMIT             = 250_000   # SB/DVBE, no formal bid, any funding (SSPR FAQ)
SMALL_BUSINESS_FEDERAL_SSPR_LIMIT = 100_000  # but the SSPR form's federal SB box says "Only <$100K"
SMALL_BUSINESS_TWO_QUOTES_AT     = 100_000   # BUS-43: 1 quote under $100K, 2 quotes for $100K-$250K

# SSPR form
SSPR_FEDERAL_CONTRACT = 15_000
SSPR_FEDERAL_GRANT    = 50_000
SSPR_NON_FEDERAL      = 100_000

# other
CERTIFIED_COST_PRICING_THRESHOLD = 2_500_000
ANTI_LOBBYING_THRESHOLD          = 100_000

FEDERAL_SOLE_SOURCE_JUSTIFICATIONS = {
    "one_of_a_kind": "One-of-a-kind",
    "emergency": "Emergency",
    "awarding_agency_approval": "Awarding Agency Approval",
    "no_competition": "No Competition (grant and cooperative agreement funds only)",
}
NON_FEDERAL_SOLE_SOURCE_JUSTIFICATIONS = {
    "one_of_a_kind": "One-of-a-kind/Unique",
    "match_existing": "Match existing (list UC PO#)",
}
DISALLOWED_JUSTIFICATIONS = {
    "pre_work": "Pre-work with the selected supplier to customize the equipment, thereby excluding "
                "competition, is not an allowable justification.",
    "price": "Price is not an allowable sole source justification.",
    "brand": "Brand name is not an allowable sole source justification.",
    "familiarity": "Staff familiarity or preference is not an allowable sole source justification; "
                   "sole source requires that only one supplier can meet the requirement.",
    "geographic": "Geographical preference is not an allowable justification for federal funds.",
}

NON_FEDERAL_ONLY_SELECTIONS = ("professional_services", "urgent")

SSPR_SECTIONS = {
    ("competitive_bid", True):        ["I", "VII", "VIII"],
    ("competitive_bid", False):       ["I", "VII", "VIII"],
    ("competitive_proposals", True):  ["I", "II", "VII", "VIII"],
    ("sole_source", True):            ["I", "III", "IV", "VII", "VIII"],
    # the form literally says non-federal sole source = "Complete III - VIII"
    ("sole_source", False):           ["I", "III", "IV", "V", "VI", "VII", "VIII"],
    ("small_business", True):         ["I", "III", "VII", "VIII"],
    ("small_business", False):        ["I", "III", "VII", "VIII"],
    ("professional_services", False): ["I", "III", "V", "VII", "VIII"],
    ("urgent", False):                ["I", "VI", "VII", "VIII"],
}


@dataclass
class ThresholdDetermination:
    evaluated_value: float
    value_basis: str
    competitive_bid_required: bool
    bid_threshold_exceeded: bool
    bid_exemption: Optional[str]
    sspr_required: bool
    sspr_threshold: float
    source_selection: str
    sspr_sections: list
    certified_cost_pricing_required: Optional[bool]
    small_business_quotes: Optional[int] = None
    explanations: list = field(default_factory=list)
    flags: list = field(default_factory=list)


def sspr_threshold_for(funding: FundingDetermination) -> float:
    if not funding.federal_rules_apply:
        return SSPR_NON_FEDERAL
    return SSPR_FEDERAL_CONTRACT if funding.award_type == "contract" else SSPR_FEDERAL_GRANT


def evaluated_value(req: PurchaseRequest, funding: FundingDetermination, aggregate: float) -> tuple[float, str]:
    # federal -> total anticipated value over all the years (UG/FAR)
    # non-federal -> annual amount (BUS-43 says "more than $100,000 annually")
    # aggregate already includes any related orders
    if req.contract_years > 1:
        if funding.federal_rules_apply:
            return aggregate, (f"total anticipated value over {req.contract_years:g} years "
                               "(federal rules use anticipated contract value)")
        annual = aggregate / req.contract_years
        return annual, f"annual expenditure (BUS-43 uses annual value; {req.contract_years:g}-year total ${aggregate:,.0f})"
    if aggregate != req.amount:
        return aggregate, "combined value of related orders"
    return aggregate, "purchase value"


def check_sole_source(req: PurchaseRequest, funding: FundingDetermination) -> tuple[bool, list]:
    # returns (is the justification ok, flags)
    flags = []
    j = req.sole_source_justification
    allowed = FEDERAL_SOLE_SOURCE_JUSTIFICATIONS if funding.federal_rules_apply else NON_FEDERAL_SOLE_SOURCE_JUSTIFICATIONS
    allowed_list = ", ".join(allowed.values())

    if j in DISALLOWED_JUSTIFICATIONS and not (j == "geographic" and not funding.federal_rules_apply):
        flags.append(Flag("SOLE_SOURCE_INVALID", "block",
                          DISALLOWED_JUSTIFICATIONS[j] + f" Allowable justifications: {allowed_list}.",
                          "SSPR Form Section IV"))
        return False, flags
    if j == "no_competition" and funding.award_type != "grant":
        flags.append(Flag("SOLE_SOURCE_INVALID", "block",
                          "'No Competition' is only available for federal grant and cooperative agreement funds.",
                          "SSPR Form Section IV"))
        return False, flags
    if j is not None and j not in allowed and j not in DISALLOWED_JUSTIFICATIONS:
        flags.append(Flag("SOLE_SOURCE_INVALID", "block",
                          f"'{j}' is not an allowable sole source justification for this funding. "
                          f"Allowable: {allowed_list}.", "SSPR Form Section IV"))
        return False, flags
    if j is None:
        flags.append(Flag("SOLE_SOURCE_JUSTIFICATION", "require",
                          f"Sole source must be documented with an allowable justification in SSPR "
                          f"Section IV: {allowed_list}. Price, brand name, and pre-work with the supplier "
                          "that excludes competition are NOT allowable.", "SSPR Form Section IV"))
    return True, flags


def evaluate_thresholds(req: PurchaseRequest, funding: FundingDetermination,
                        aggregate: Optional[float] = None) -> ThresholdDetermination:
    aggregate = req.amount if aggregate is None else aggregate
    value, basis = evaluated_value(req, funding, aggregate)
    federal = funding.federal_rules_apply
    flags, notes = [], []

    over_bid = value >= COMPETITIVE_BID_THRESHOLD
    selection = req.source_selection
    exemption = None
    sb_quotes = None

    # prof services / urgent are non-federal only on the SSPR form
    if federal and selection in NON_FEDERAL_ONLY_SELECTIONS:
        label = "Professional/personal services" if selection == "professional_services" else "Unusual & compelling urgency"
        flags.append(Flag("SELECTION_NOT_ALLOWED", "block",
                          f"{label} is only available for non-federal funds; it cannot be used when "
                          "federal rules apply.", "SSPR Form Section I"))
        selection = None

    if selection == "sole_source":
        ok, ss_flags = check_sole_source(req, funding)
        flags += ss_flags
        if ok:
            exemption = "sole source (with allowable SSPR Section IV justification)"
        else:
            selection = None
    elif selection == "small_business":
        if value < SMALL_BUSINESS_LIMIT:
            exemption = "certified small business / DVBE (under $250,000)"
            sb_quotes = 2 if value >= SMALL_BUSINESS_TWO_QUOTES_AT else 1
            if federal and value >= SMALL_BUSINESS_FEDERAL_SSPR_LIMIT:
                flags.append(Flag("SB_FEDERAL_OVER_100K", "caution",
                                  "The SSPR FAQ allows SB/DVBE awards up to $250,000 with any funding source, "
                                  "but the SSPR form's federal Certified Small Business option is limited to "
                                  "purchases under $100,000. Confirm the source selection with Procurement.",
                                  "SSPR FAQ; SSPR Form Section I"))
        else:
            flags.append(Flag("SB_LIMIT_EXCEEDED", "require",
                              f"At ${value:,.0f} this exceeds the $250,000 small business/DVBE limit, so the "
                              "small business exception does not apply and a competitive bid is required.",
                              "BUS-43; CA PCC 10508.5"))
            selection = None
    elif selection in NON_FEDERAL_ONLY_SELECTIONS:
        exemption = {"professional_services": "professional/personal services (non-federal only)",
                     "urgent": "unusual & compelling urgency (non-federal only)"}[selection]

    bid_required = over_bid and exemption is None

    if selection is None:
        if bid_required:
            selection = "competitive_bid"
        elif federal:
            selection = "competitive_proposals"
        else:
            selection = "competitive_bid"

    if over_bid:
        notes.append(f"At ${value:,.0f} ({basis}), this meets/exceeds the ${COMPETITIVE_BID_THRESHOLD:,} "
                     "competitive bid threshold.")
        if exemption:
            notes.append(f"Competitive bid exemption applies: {exemption}.")
    else:
        notes.append(f"At ${value:,.0f} ({basis}), this is below the ${COMPETITIVE_BID_THRESHOLD:,} "
                     "competitive bid threshold.")
    if federal:
        notes.append(f"The federal bid threshold for UC is also ${COMPETITIVE_BID_THRESHOLD:,}: CA Public Contract "
                     f"Code is stricter than the ${SIMPLIFIED_ACQUISITION_THRESHOLD:,} federal Simplified "
                     "Acquisition Threshold, and the stricter rule applies.")
    if req.contract_years > 1 and not federal and (aggregate >= COMPETITIVE_BID_THRESHOLD > value):
        notes.append(f"Note: under Uniform Guidance/FAR the ${aggregate:,.0f} total would require a bid; BUS-43 "
                     "only compels a bid for annual expenditures of $100,000 or more. Seeking competition is "
                     "still encouraged.")
    if sb_quotes:
        notes.append(f"Small business/DVBE: obtain {sb_quotes} quote{'s' if sb_quotes > 1 else ''} from certified "
                     "small businesses/DVBEs (BUS-43: 1 quote for $10K-$100K, 2 quotes for $100K-$250K).")

    # SSPR
    sspr_thr = sspr_threshold_for(funding)
    sspr_required = value >= sspr_thr
    sspr_label = {SSPR_NON_FEDERAL: "non-federal", SSPR_FEDERAL_GRANT: "federal grant/cooperative agreement",
                  SSPR_FEDERAL_CONTRACT: "federal contract"}[sspr_thr]
    notes.append(f"SSPR form threshold for {sspr_label} purchases is ${sspr_thr:,.0f}: SSPR "
                 f"{'IS' if sspr_required else 'is NOT'} required.")
    if federal and funding.award_type == "grant" and not sspr_required and value >= FEDERAL_MICRO_PURCHASE:
        notes.append(f"(Campuses may set a grant/cooperative agreement micro-purchase threshold up to "
                     f"${CAMPUS_GRANT_MICRO_PURCHASE_MAX:,}, per OMB guidance.)")

    sections = []
    if sspr_required:
        key = (selection, federal)
        sections = SSPR_SECTIONS.get(key) or SSPR_SECTIONS[("competitive_bid", federal)]

    # certified cost or pricing data (FAR 15.403-4)
    ccpd = None
    if federal and funding.award_type == "contract" and selection == "sole_source" \
            and value >= CERTIFIED_COST_PRICING_THRESHOLD:
        ccpd = req.commercial_item is not True
        if ccpd:
            msg = ("Sole-sourced federal non-commercial contract order of $2,500,000 or more: the supplier must "
                   "submit certified cost or pricing data (FAR 15.403-4).")
            if req.commercial_item is None:
                msg += " (Not required if the item is a commercial item.)"
            flags.append(Flag("CERTIFIED_COST_PRICING", "require", msg, "FAR 15.403-4; SSPR Form Section III"))

    return ThresholdDetermination(
        evaluated_value=value, value_basis=basis,
        competitive_bid_required=bid_required, bid_threshold_exceeded=over_bid,
        bid_exemption=exemption, sspr_required=sspr_required, sspr_threshold=sspr_thr,
        source_selection=selection, sspr_sections=sections,
        certified_cost_pricing_required=ccpd, small_business_quotes=sb_quotes,
        explanations=notes, flags=flags,
    )


def detect_split_order(req: PurchaseRequest, funding: FundingDetermination) -> list:
    # BUS-43: "Requirements shall not be artificially divided into separate transactions
    # to avoid competition." flag it when each order is under a threshold but the total isn't
    orders = [req.amount] + [float(o) for o in req.related_orders]
    if len(orders) < 2 and not req.split_intent:
        return []
    total = sum(orders)
    flags = []
    thresholds = [(COMPETITIVE_BID_THRESHOLD, "competitive bid")]
    sspr_thr = sspr_threshold_for(funding)
    if sspr_thr != COMPETITIVE_BID_THRESHOLD:
        thresholds.append((sspr_thr, "SSPR form"))

    orders_txt = " + ".join(f"${o:,.0f}" for o in orders)
    for thr, label in thresholds:
        if len(orders) >= 2 and all(o < thr for o in orders) and total >= thr:
            flags.append(Flag("SPLIT_ORDER", "block",
                              f"Potential split order: {orders_txt} = ${total:,.0f}. Each order is below the "
                              f"${thr:,.0f} {label} threshold but together they meet it. Requirements must not "
                              "be artificially divided to avoid competition; treat this as one "
                              f"${total:,.0f} procurement.", "BUS-43"))
    if not flags and req.split_intent:
        flags.append(Flag("SPLIT_ORDER", "block",
                          "Intentionally dividing a purchase into smaller orders to avoid bidding requirements "
                          f"is prohibited under BUS-43. For reference, the combined value is ${total:,.0f}; the "
                          f"competitive bid threshold is ${COMPETITIVE_BID_THRESHOLD:,}.", "BUS-43"))
    return flags
