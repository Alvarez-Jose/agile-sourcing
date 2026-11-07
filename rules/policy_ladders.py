# rules/policy_ladders.py
# decision ladders for policy areas that have crisp, citable answers but no dollar threshold:
#   post-employment contracting bans   (OGC post-employment rules, PCC 10411 / 10517)
#   business meal documentation         (BUS-79 IV.B)
#   tax-free alcohol permits            (BFB-BUS-2 / UCPS 120031)
#   certificate of insurance by risk    (BUS-63 Risk Matrix)
#
# each ladder reads the question text, walks its conditions top to bottom and returns a
# determination with a one-line headline, the explanation and the provenance keys it relied
# on (rules/provenance.py). like the threshold rules, the headline goes into the answer
# word for word so the LLM can explain it but not change it.

import re
from dataclasses import dataclass, field

# post-employment ---------------------------------------------------------------------------
FORMER_EMPLOYEE = re.compile(
    r"former (uc |university |campus )?(employee|staff|official|director|manager|dean|chancellor)|ex-?employee"
    r"|\bretire[ds]?\b|\bretiree|\bretiring\b|left (the )?(university|uc)\b|post-?employment|after (leaving|retir\w+)"
    r"|used to work (at|for) (uc|the university)|recently (left|departed|separated)|no longer (works?|employed)", re.I)
DECISION_MAKING = re.compile(
    r"negotiat|\bplanning\b|arrangements?|decision-?making|part of the decision|(helped|involved in) (select|choos|"
    r"evaluat|award|draft|write|writ|develop)|wrote the (spec|rfp|rfq|requirements)|evaluated (the )?(bids?|proposals?)"
    r"|managed (the|this) (contract|vendor|supplier)|approved (the )?(contract|purchase|award)|on the (selection|"
    r"evaluation) (committee|panel)", re.I)
POLICYMAKING = re.compile(
    r"policy-?making|\b(director|dean|chancellor|provost|vice president|chief|department head|head of|associate vice|"
    r"assistant vice|manager|supervisor)\b", re.I)
SAME_DEPARTMENT = re.compile(
    r"same department|(their|his|her) (former|old|previous) (department|unit|office)|department (he|she|they) "
    r"(left|worked|used to work|came from)|(the|our) department (that )?(he|she|they) (was|were) in|back into "
    r"(the|their) (own )?department|former (department|unit)", re.I)
CONTRACTING_CONTEXT = re.compile(r"\b(contract\w*|hire|hiring|hired|bid\w*|vendor|supplier|consult\w*|award\w*|"
                                 r"procure\w*|rfp|rfq|purchase order|ban|post-?employment)\b", re.I)
REPRESENTING_OTHERS = re.compile(
    r"represent(ing)? (another|a|the|an outside) (person|party|company|vendor|supplier|client|firm)|appear(ing)? "
    r"before|lobby|on behalf of (a|an|the|another) (vendor|company|client|supplier|firm)", re.I)

# business meals ----------------------------------------------------------------------------
INSURANCE_QUESTION = re.compile(r"\binsurance\b|\bindemnif|\bliability (policy|limit|coverage|insurance)|"
                                r"per occurrence", re.I)
BUSINESS_MEAL = re.compile(
    r"business (meal|meeting|lunch|dinner|breakfast)|entertainment (expense|event|check request)|meal expense"
    r"|\b(catering|caterer|reception|banquet|refreshments)\b|(lunch|dinner|breakfast|meal)s? (for|with|at) "
    r"|hospitality expense|working (lunch|dinner)", re.I)

# tax-free alcohol --------------------------------------------------------------------------
ALCOHOL = re.compile(r"tax-?free (alcohol|permit)|alcohol (permit|use permit)|\b(190|200)-?proof\b|\bethanol\b|\bttb\b"
                     r"|alcohol free of tax", re.I)
MENTIONS_DEA = re.compile(r"\bdea\b", re.I)
INVENTORY_OVERDUE = re.compile(r"(haven'?t|have not|hasn'?t|has not|no|never|without|last) .{0,40}inventory|"
                               r"inventory .{0,40}(last year|a year ago|over (six|6) months|overdue|annual)|"
                               r"annual inventory", re.I)
INVENTORY_SCHEDULED = re.compile(r"inventory (is )?(scheduled|planned|set|booked) (for )?(next|this|in|on)|"
                                 r"(next|this) (week|month).{0,30}inventory|inventory.{0,30}(next|this) (week|month)",
                                 re.I)
PERMIT_HOLDER_LEAVING = re.compile(r"(pi|investigator|holder|professor|faculty).{0,60}(retir|leav|depart)"
                                   r"|(retir|leav|depart).{0,60}(pi\b|investigator|permit)", re.I)

# BUS-63 risk matrix ------------------------------------------------------------------------
RISK_MATRIX_QUESTION = re.compile(r"certificate of insurance|\bcoi\b|risk matrix|risk level|risk exposure|"
                                  r"(high|moderate|low)[- ]risk", re.I)
# exposures C-K: any one of them makes the whole contract High risk -> COI must be collected
HIGH_RISK_EXPOSURES = [
    ("C. Digital Risk - High", re.compile(r"\bp3\b|\bp4\b|protected level [34]|\b(phi|hipaa|ssn|social security "
                                          r"numbers?|credit card|payment card|pci)\b|vra.{0,30}(high|critical)", re.I)),
    ("D. Physical Safety or Security Risk", re.compile(r"construction|renovation|hazardous|biohazard|chemical|"
                                                       r"security (guard|service)|building maintenance|elevator|"
                                                       r"scaffold|demolition|asbestos|electrical work", re.I)),
    ("E. Professional Services", re.compile(r"\b(medical|legal|accounting|architect\w*|engineering) services?\b|"
                                            r"\b(attorney|law firm|cpa|auditor|architect|engineer)s?\b", re.I)),
    ("F. Products - Controlled Substances / Medical Devices", re.compile(
        r"controlled substance|medical device|implant|prescription|human stem cell|critical care equipment", re.I)),
    ("G. International", re.compile(r"\binternational\b|overseas|foreign (entity|vendor|company|supplier)|outside "
                                    r"(of )?the (u\.?s\.?|united states)|abroad", re.I)),
    ("H. Students or Minors", re.compile(r"\bminors?\b|under (18|eighteen)|\bstudents?\b.{0,40}(supervis|care|"
                                         r"custody|camp|field trip)|(camp|field trip|tutoring|youth program)", re.I)),
    ("I. Use of Facilities", re.compile(r"use of (uc |university |our )?(facilit|space|building|room|field|"
                                        r"auditorium)|facilit(y|ies) use agreement|\blease\b|rent(ing)? (our|uc|"
                                        r"university|campus) (space|facilit|building)", re.I)),
    ("J. Financial Assets", re.compile(r"\bcash\b|cash equivalent|bank account|investment|revenue shar|handle(s|d)? "
                                       r"(uc |university )?(money|funds|payments)|point of sale|ticket sales", re.I)),
    ("K. Transportation", re.compile(r"\btransport(ing|ation)?\b|\bshuttle\b|\bbus(es)?\b|charter|drive (students|"
                                     r"staff|faculty)|\bdriver\b", re.I)),
]
MODERATE_DIGITAL = re.compile(r"\bp2\b|protected level 2|generative (ai|artificial)|\bai\b (model|tool|service)|"
                              r"third-?party analytics|vra.{0,30}moderate", re.I)
LOW_DIGITAL = re.compile(r"\bp1\b|protected level 1|public data|vra.{0,30}(minimal|low)", re.I)


@dataclass
class LadderDetermination:
    code: str
    severity: str            # block / require / info
    headline: str            # goes into the answer header word for word
    lines: list              # the ladder, in the order it was walked
    source_keys: list        # rules/provenance.py keys
    policy: str
    conditions: list = field(default_factory=list)   # extra lines for the LLM's Conditions section


def evaluate_post_employment(text: str):
    if not text or not FORMER_EMPLOYEE.search(text) or not CONTRACTING_CONTEXT.search(text):
        return None
    decision = bool(DECISION_MAKING.search(text))
    policymaking = bool(POLICYMAKING.search(text))
    same_dept = bool(SAME_DEPARTMENT.search(text))
    retiree = bool(re.search(r"\bretire", text, re.I))
    representing = bool(REPRESENTING_OTHERS.search(text))

    ladder = [
        "Post-employment contracting bans (Public Contract Code, OGC post-employment rules): "
        "(1) TWO YEARS - no contract with the University to provide goods or services if the person took part in "
        "any negotiations, planning, arrangements or decision-making for that contract while employed; "
        "(2) 12 MONTHS - no contract with the department they left if they held a policymaking position there in "
        "the same general subject area; (3) retirees are generally exempt from both bans and may be hired back; "
        "(4) the separate ONE-YEAR rule bars representing another party before the University for pay - it is "
        "not a contracting ban. The source of the project's funding does not change any of this.",
    ]
    keys = ["POST_EMPLOYMENT_TWO_YEAR", "POST_EMPLOYMENT_12_MONTH", "POST_EMPLOYMENT_RETIREE",
            "POST_EMPLOYMENT_ONE_YEAR_REPRESENTING"]
    if retiree and not representing:
        headline = ("Retirees are generally exempt from the two-year and 12-month contracting bans and may be hired "
                    "back by the University; confirm with the campus conflict-of-interest office.")
        severity = "require"
    elif decision:
        headline = ("PROHIBITED for two years after leaving: the former employee took part in the negotiations, "
                    "planning or decision-making for this contract while at UC (Public Contract Code; OGC "
                    "post-employment rules 3(a)).")
        severity = "block"
    elif policymaking and same_dept:
        headline = ("PROHIBITED for 12 months after leaving: contracting with the department the former employee "
                    "left, where they held a policymaking position in the same subject area (OGC post-employment "
                    "rules 3(b)).")
        severity = "block"
    elif representing:
        headline = ("One-year ban applies: for one year after leaving, a former employee may not appear before or "
                    "communicate with their campus while representing another party for pay to influence a "
                    "University proceeding.")
        severity = "block"
    else:
        headline = ("No contracting ban is triggered on the facts given, but check both bans before contracting: "
                    "two years if the former employee took part in the decision-making for this contract, 12 "
                    "months if they held a policymaking position in the contracting department; retirees are "
                    "generally exempt. The project's funding source is irrelevant.")
        severity = "require"
    return LadderDetermination("POST_EMPLOYMENT", severity, headline, ladder, keys,
                               "Public Contract Code 10411/10517; OGC Post-Employment Rules (Oct 2023)",
                               conditions=["Ask the campus conflict-of-interest office to confirm the person's "
                                           "prior role and whether an exemption applies."])


def evaluate_business_meal(text: str):
    if not text or not BUSINESS_MEAL.search(text):
        return None
    # an insurance question about a caterer (benchmark Q38) is not a documentation question
    if INSURANCE_QUESTION.search(text) and not re.search(r"document|reimburs|receipt|expense|claim|approv", text, re.I):
        return None
    headline = ("Documentation required for a business meal or entertainment expense (BUS-79): type of expense; "
                "type of event; number of participants with a guest list giving each participant's name, title "
                "and occupation or group affiliation; date and location; the business-related purpose of the "
                "occasion; and the signature, printed name and department of the approving authority (plus the "
                "host's signature for entertainment, recruitment and morale-building events). Expenses of $75 or "
                "more per occasion need original itemized receipts.")
    return LadderDetermination("BUSINESS_MEAL_DOCS", "require", headline,
                               ["BUS-79 IV.B.1: the reimbursement, recharge or payment request must carry all of "
                                "the items above; the two that establish the business relationship are the "
                                "purpose of the occasion and the guest list with names and titles."],
                               ["BUS79_DOCUMENTATION", "BUS79_GUEST_LIST", "BUS79_PURPOSE", "BUS79_RECEIPTS"],
                               "BFB-BUS-79 IV.B")


def evaluate_alcohol_permit(text: str):
    if not text or not ALCOHOL.search(text):
        return None
    lines = [
        "Tax-free alcohol permits (BFB-BUS-2 / UCPS 120031): (1) the application for an industrial use permit is "
        "filed with the Alcohol and Tobacco Tax and Trade Bureau (TTB), in the name of The Regents of the "
        "University of California; (2) TTB approves it and issues the numbered Permit to Use Alcohol Free of Tax "
        "(Form 5150.22), which is continuous unless terminated; (3) no shipment may be made until the vendor has "
        "a signed copy of the valid permit on file; (4) a physical inventory is taken semiannually (about every "
        "six months); (5) authorized persons sign a receipt for each delivery and keep complete records of all "
        "tax-free alcohol received and issued; (6) tax-free alcohol is used only on University premises.",
    ]
    keys = ["ALCOHOL_TTB_APPLICATION", "ALCOHOL_REGENTS_NAME", "ALCOHOL_TTB_PERMIT", "ALCOHOL_PERMIT_CONTINUOUS",
            "ALCOHOL_VENDOR_PERMIT_ON_FILE", "ALCOHOL_SEMIANNUAL_INVENTORY", "ALCOHOL_RECORDS",
            "ALCOHOL_PREMISES_ONLY"]
    conditions = []
    headline = ("Tax-free alcohol is bought under the University's TTB permit, held in the name of The Regents: "
                "the vendor must have a signed copy of the valid permit on file, inventories are semiannual, and "
                "receipts and records are kept for every delivery.")
    if MENTIONS_DEA.search(text):
        conditions.append("A DEA registration is not the credential for tax-free alcohol; DEA registration governs "
                          "controlled substances (BUS-50). The tax-free alcohol permit is the TTB permit.")
    if INVENTORY_SCHEDULED.search(text):
        conditions.append("Inventories are semiannual, not annual, and an upcoming scheduled inventory does not "
                          "block withdrawals under the permit in the meantime, provided the last physical inventory "
                          "was within about six months. The dollar amount of the order is irrelevant.")
    elif INVENTORY_OVERDUE.search(text):
        conditions.append("The inventory requirement is semiannual, not annual: if the last physical inventory was "
                          "more than about six months ago it is overdue and should be taken before further "
                          "withdrawals.")
    if PERMIT_HOLDER_LEAVING.search(text):
        conditions.append("The permit belongs to The Regents, not to an individual investigator, and is continuous, "
                          "so a permit holder's retirement or departure does not invalidate it; update the "
                          "campus's authorized-person list.")
    return LadderDetermination("ALCOHOL_PERMIT", "require", headline, lines, keys,
                               "BFB-BUS-2 / UCPS 120031 Tax-Free Alcohol Permits", conditions=conditions)


def evaluate_risk_matrix(text: str):
    if not text:
        return None
    exposures = [name for name, pat in HIGH_RISK_EXPOSURES if pat.search(text)]
    asks_matrix = bool(RISK_MATRIX_QUESTION.search(text))
    if not asks_matrix and not (INSURANCE_QUESTION.search(text) and exposures):
        return None
    ladder = ["BUS-63 Risk Matrix: exposures C-K (digital risk - high; physical safety or security; professional "
              "services; controlled substances / medical devices; international; students or minors; use of UC "
              "facilities; financial assets; transportation) make the ENTIRE contract High risk and a Certificate "
              "of Insurance (COI) must be collected. Exposure A (digital risk - low) is Low risk and B (digital "
              "risk - moderate) is Moderate risk: a COI does not need to be collected, but the agreement or PO "
              "must require the contractor to provide one on request. Digital risk: P3/P4 data or a high/critical "
              "VRA = high; P2 data, generative AI / third-party analytics, or a moderate VRA = moderate; P1 data "
              "or a minimal VRA = low. The local Risk Management office makes the final call."]
    keys = ["RISK_MATRIX_HIGH_COI", "RISK_MATRIX_LOW_MODERATE_COI"]
    if exposures:
        headline = (f"High risk under the BUS-63 Risk Matrix ({'; '.join(exposures)}): a Certificate of Insurance "
                    "must be collected before the contract is executed.")
        severity = "require"
    elif MODERATE_DIGITAL.search(text):
        headline = ("Moderate risk under the BUS-63 Risk Matrix (digital risk - moderate): a Certificate of "
                    "Insurance does not need to be collected, but the agreement must require the contractor to "
                    "provide one on request.")
        severity = "require"
    elif LOW_DIGITAL.search(text):
        headline = ("Low risk under the BUS-63 Risk Matrix (digital risk - low): a Certificate of Insurance does "
                    "not need to be collected, but the agreement must require the contractor to provide one on "
                    "request.")
        severity = "require"
    else:
        headline = ("Certificate of Insurance rule (BUS-63 Risk Matrix): required whenever the contract involves "
                    "any High-risk exposure C-K; for Low or Moderate risk (digital risk only) it is not collected "
                    "but must be available on request.")
        severity = "require"
    return LadderDetermination("RISK_MATRIX_COI", severity, headline, ladder, keys, "BUS-63 Risk Matrix (9.19.2025)",
                               conditions=["The BUS-63 policy itself does not set dollar minimums; insurance limits "
                                           "are in the UC Terms and Conditions of Purchase (insurance article)."])


LADDERS = {
    "post_employment": evaluate_post_employment,
    "business_meal": evaluate_business_meal,
    "alcohol_permit": evaluate_alcohol_permit,
    "risk_matrix": evaluate_risk_matrix,
}


def evaluate_ladders(text: str, topics=None) -> list:
    # topics (from rules/query_parser.py) narrow which ladders are tried; with no topics every
    # ladder looks at the text itself
    out = []
    for topic, fn in LADDERS.items():
        if topics is not None and topic not in topics:
            continue
        det = fn(text)
        if det:
            out.append(det)
    return out
