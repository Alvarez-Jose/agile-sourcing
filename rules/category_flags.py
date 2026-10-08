# rules/category_flags.py
# stuff that depends on WHAT is being bought rather than how much:
#   covered services / contracting out (Regents 5402 + AFSCME 3299 Article 5)
#   equipment tagging (BUS-29)
#   data security appendix, BAA, IS-3
#   plus info flags for BUS-63, BUS-79, G-41, G-13, BUS-50, UCPS 120029

import re
from dataclasses import dataclass, field
from typing import Optional

from rules.models import EquipmentItem, Flag, PurchaseRequest

# covered services (Regents 5402 / Article 5)
COVERED_SERVICES = {
    "cleaning":            [r"\bcleaning\b"],
    "custodial":           [r"\bcustodial\b", r"\bcustodian"],
    "janitorial":          [r"\bjanitor"],
    "housekeeping":        [r"\bhousekeeping\b"],
    "food services":       [r"\bfood service", r"\bcafeteria\b", r"\bdining service", r"\bdining hall"],
    "laundry":             [r"\blaundry\b"],
    "grounds keeping":     [r"\bgrounds ?keep", r"\blandscap(e|ing) (maintenance|services?)", r"\bgardening\b"],
    "building maintenance": [r"\bbuilding maintenance\b", r"\bfacilit(y|ies) maintenance\b"],
    "transportation":      [r"\bshuttle\b", r"\btransportation services?\b", r"\bbus (drivers?|services?)\b"],
    "parking":             [r"\bparking (services?|attendants?|enforcement|operations?)\b", r"\bvalet\b"],
    "security":            [r"\bsecurity (guards?|officers?|services?|patrols?)\b", r"\bguard services?\b"],
    "nursing assistant":   [r"\bnursing assistant", r"\bcertified nursing"],
    "medical imaging":     [r"\bmedical imaging\b", r"\bradiology tech", r"\bimaging tech"],
    "medical technician":  [r"\bmedical tech", r"\blab(oratory)? tech", r"\bpatient care tech"],
}
# "security" shows up in IT questions too (data security etc), those aren't guard services
NOT_GUARD_SECURITY = re.compile(r"\b(data|information|cyber|network|it|cloud|application|software)\s+security\b", re.I)
SKILLED_CRAFTS = re.compile(r"\b(electric(al|ian)|plumb(ing|er)|hvac|carpent|elevator|roofing|welding|skilled craft)", re.I)

CONTRACTING_OUT_EXCEPTIONS = {
    "emergency": "Emergency",
    "insufficient_staff": "Insufficient UC staff to perform the work",
    "specialized_expertise": "Specialized expertise/equipment not available internally",
    "incidental_to_lease": "Services incidental to a property lease",
    "urgent_temporary": "Urgent, temporary, or occasional need",
    "remote_facility": "Remote facility (more than 10 miles from campus)",
    "registry_personnel": "Registry personnel in clinical operations",
    "required_by_law": "Required by law, federal requirement, or court order",
}
AFSCME_NOTICE_THRESHOLD = 100_000   # over $100K
WAGE_PARITY_MIN_DAYS = 90           # over 90 days

# equipment (BUS-29)
EQUIPMENT_TAG_THRESHOLD = 5_000
EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004 = 1_500

# data / IT
DATA_PATTERNS = re.compile(
    r"\b(institutional data|uc data|university data|student (data|records?|information)|personal (data|information)"
    r"|pii\b|employee (data|records?)|research data|confidential data|access(es|ing)? (our|uc|university|campus) "
    r"(data|systems?|records?)|data access|(access|handle|store|process)(es|ing)? .{0,20}data)", re.I)
PHI_PATTERNS = re.compile(r"\b(phi\b|protected health|hipaa|patient (data|records?|information)|medical records?"
                          r"|health information)", re.I)
DEIDENTIFIED = re.compile(r"\b(de-?identified|anonymi[sz]ed)\b", re.I)
IT_PATTERNS = re.compile(r"\b(it (services?|consult\w*|contract)|software|saas|cloud|hosting|hosted|web ?site|"
                         r"database|information system|records system|it support|platform|app(lication)? development)",
                         re.I)

# info-only flags, just point people at the right policy
ADVISORY_CATEGORIES = [
    ("BUS79", re.compile(r"\b(catering|caterer|meal|lunch|dinner|breakfast|entertainment|reception|banquet|business meeting)", re.I),
     "BUS-79", "Business meetings and entertainment: document business purpose and names of all attendees; "
               "meal/entertainment limits apply."),
    ("G41", re.compile(r"\b(gift cards?|employee (award|gift)s?|non-cash award|recognition award)", re.I),
     "BFB-G-41", "Employee non-cash awards and gifts are governed by G-41 (limits and eligibility apply)."),
    ("G13", re.compile(r"\b(moving|relocation|relocate)\b", re.I),
     "BFB-G-13", "Moving and relocation expenses are governed by G-13."),
    ("BUS50", re.compile(r"\b(controlled substances?|dea\b|narcotic|schedule (i|ii|iii|iv|v)\b|opioid|ketamine|fentanyl)", re.I),
     "BUS-50", "Controlled substances require DEA registration, a Controlled Substances Program Officer (CSPO), "
               "and RAPC approval where applicable."),
    ("VEHICLE", re.compile(r"\b(vehicles?|trucks?|vans?|cars?|golf carts?|fleet)\b", re.I),
     "UCPS 120029", "University vehicle acquisitions and dispositions are governed by UCPS 120029."),
]
SERVICE_PATTERNS = re.compile(r"\b(services?|contractor|consult\w*|vendor on.?site|on.?site|install\w*|event|catering|"
                              r"repair|maintenance)\b", re.I)


@dataclass
class EquipmentDetermination:
    item: EquipmentItem
    threshold: float
    must_tag: bool
    explanation: str


@dataclass
class CoveredServiceDetermination:
    services: list
    prohibited: bool
    exception: Optional[str]
    afscme_notice_required: bool
    wage_parity_required: bool
    explanations: list = field(default_factory=list)


@dataclass
class CategoryResult:
    covered_service: Optional[CoveredServiceDetermination] = None
    equipment: list = field(default_factory=list)
    needs_data_security_appendix: bool = False
    needs_baa: bool = False
    needs_is3: bool = False
    flags: list = field(default_factory=list)


def detect_covered_services(text: str) -> list:
    if not text:
        return []
    found = []
    for service, patterns in COVERED_SERVICES.items():
        if any(re.search(p, text, re.I) for p in patterns):
            if service == "security" and NOT_GUARD_SECURITY.search(text) and not re.search(r"\bguard|\bpatrol", text, re.I):
                continue
            if service == "building maintenance" and SKILLED_CRAFTS.search(text):
                continue
            found.append(service)
    return found


def evaluate_covered_services(req: PurchaseRequest) -> Optional[CoveredServiceDetermination]:
    services = detect_covered_services(req.description)
    if not services:
        return None

    notes = [f"'{', '.join(services)}' is a covered service under Regents Policy 5402 and AFSCME 3299 Article 5. "
             "The University generally prohibits contracting out covered services that can be performed by "
             "UC employees."]
    exc = req.contracting_out_exception
    exc_label = CONTRACTING_OUT_EXCEPTIONS.get(exc) if exc else None

    prohibited = False
    if req.displaces_uc_employees:
        prohibited = True
        notes.append("PROHIBITED: the contract would displace UC employees. Displacement (demotion, layoff, or "
                     "involuntary reduction in time due to the contract) is not permitted under Regents "
                     "Policy 5402, regardless of contract value.")
    elif exc and not exc_label:
        prohibited = True
        notes.append(f"'{exc}' is not a recognized exception; the contract is prohibited unless a listed "
                     "exception applies.")
    elif exc_label:
        notes.append(f"Claimed exception: {exc_label}. Contracting out may be permitted if this exception is "
                     "documented, and it must not displace UC employees.")
    else:
        notes.append("Contracting out is permitted ONLY if a listed exception applies: "
                     + "; ".join(CONTRACTING_OUT_EXCEPTIONS.values())
                     + ". If none applies, the contract is prohibited.")

    notice = req.amount > AFSCME_NOTICE_THRESHOLD
    parity = notice and req.term_days > WAGE_PARITY_MIN_DAYS
    if notice:
        notes.append(f"At ${req.amount:,.0f} (over ${AFSCME_NOTICE_THRESHOLD:,}), AFSCME 3299 must be notified "
                     "before entering, extending, or renewing the contract: 30 calendar days' notice (if no RFP) "
                     "or a copy of the RFP at issuance. AFSCME has 14 calendar days to respond.")
    else:
        notes.append(f"At ${req.amount:,.0f} (not over ${AFSCME_NOTICE_THRESHOLD:,}), AFSCME 3299 advance notice "
                     "is not required.")
    if parity:
        term = f"{req.duration_days} days" if req.duration_days is not None else f"{req.contract_years:g} year(s)"
        notes.append(f"Contract over ${AFSCME_NOTICE_THRESHOLD:,} and longer than {WAGE_PARITY_MIN_DAYS} days "
                     f"(term: {term}): the contractor must provide wages and benefits equivalent to UC employees "
                     "performing the same work (wage/benefit parity).")
    elif notice:
        notes.append(f"Term is {WAGE_PARITY_MIN_DAYS} days or less, so wage/benefit parity is not required.")

    return CoveredServiceDetermination(services, prohibited, exc_label, notice, parity, notes)


def evaluate_equipment(items: list) -> list:
    results = []
    for item in items:
        thr = EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004 if item.acquired_before_july_2004 else EQUIPMENT_TAG_THRESHOLD
        must = item.cost >= thr
        kind = "Accessory" if item.is_accessory else "Item"
        if must:
            exp = (f"{item.name} (${item.cost:,.0f}): MUST be inventoried, tagged, tracked, and assigned a CAAN - "
                   f"it meets the ${thr:,} inventorial equipment threshold (BUS-29).")
            if item.is_accessory:
                exp += " Accessories of $5,000 or more acquired after the initial purchase must also be capitalized."
        else:
            exp = (f"{item.name} (${item.cost:,.0f}): does NOT need tagging - it is below the ${thr:,} threshold "
                   "and is not inventorial equipment (BUS-29).")
        results.append(EquipmentDetermination(item, thr, must, exp))
    return results


def _mentions(flag: Optional[bool], pattern: re.Pattern, text: str) -> bool:
    return flag if flag is not None else bool(text and pattern.search(text))


def evaluate_categories(req: PurchaseRequest) -> CategoryResult:
    text = req.description or ""
    res = CategoryResult()

    res.covered_service = evaluate_covered_services(req)
    if res.covered_service:
        cs = res.covered_service
        res.flags.append(Flag("COVERED_SERVICE", "block" if cs.prohibited else "require",
                              " ".join(cs.explanations), "Regents Policy 5402; AFSCME 3299 Article 5"))

    res.equipment = evaluate_equipment(req.items)

    deidentified = bool(DEIDENTIFIED.search(text))
    phi = req.vendor_accesses_phi if req.vendor_accesses_phi is not None else \
        bool(PHI_PATTERNS.search(text)) and not deidentified
    data = _mentions(req.vendor_accesses_data, DATA_PATTERNS, text) or phi
    it = _mentions(req.it_services, IT_PATTERNS, text)

    res.needs_baa = phi
    res.needs_data_security_appendix = data
    res.needs_is3 = it and data
    if phi:
        res.flags.append(Flag("PHI", "require", "Vendor will access protected health information (PHI): a Business "
                              "Associate Agreement (BAA) is required under HIPAA.", "Appendix BAA"))
    elif deidentified and PHI_PATTERNS.search(text) and req.vendor_accesses_phi is None:
        res.flags.append(Flag("PHI_DEIDENTIFIED", "info", "Only de-identified health information is shared, so a "
                              "BAA is not required (a BAA applies when a vendor handles PHI).", "Appendix BAA"))
    if data:
        res.flags.append(Flag("DATA_SECURITY", "require", "Vendor will access UC institutional data: the Appendix "
                              "Data Security must be included in the agreement.", "Appendix Data Security"))
    if res.needs_is3:
        res.flags.append(Flag("IS3", "require", "Vendor provides IT services/software/cloud involving UC data: the "
                              "engagement must comply with UC IS-3 Electronic Information Security.", "IS-3"))

    for code, pattern, policy, msg in ADVISORY_CATEGORIES:
        if pattern.search(text):
            res.flags.append(Flag(code, "info", msg, policy))
    if SERVICE_PATTERNS.search(text) or res.covered_service:
        res.flags.append(Flag("BUS63", "info", "Review the BUS-63 Risk Matrix for the supplier's insurance "
                              "requirements (e.g., general liability limits).", "BUS-63"))
    return res
