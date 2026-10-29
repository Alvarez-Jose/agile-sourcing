# rules/provenance.py
# where every threshold in the rule engine comes from: document, version, physical PDF
# page, section and the exact quote. returned with every determination so an answer can
# show its source, and checked by rules/test_provenance.py against the actual files in
# data/raw_policies (the test fails if a quote stops appearing after a policy update).
#
# pages are physical one-based PDF pages (what a PDF viewer shows), not printed numbers.

from dataclasses import asdict, dataclass
from typing import Optional

# documents the rules cite. "files" are the names in data/raw_policies that must contain
# each quote; the first one is the version the page numbers refer to
DOCUMENTS = {
    "bus-43": dict(
        title="BFB-BUS-43: Purchases of Goods and Services; Supply Chain Management",
        version="Interim, issued/effective January 26, 2026",
        files=("BUS-43_Interim_2026-01-26.pdf",),
        url="https://policy.ucop.edu/doc/3220485/BFB-BUS-43"),
    "sspr-form": dict(
        title="Source Selection & Price Reasonableness Justification Form (SSPR)",
        version="Revised 12-2025",
        files=("SSPR_Official_UCSC_2025-12.pdf", "SOURCE SELECTION & PRICE REASONABLENESS JUSTIFICATION FORM (1).docx"),
        url="https://financial.ucsc.edu/Financial_Affairs_Forms/Source_Selection_Justification_Form.pdf"),
    "federal-funds-checklist": dict(
        title="UC Procurement Federal Funds Checklist",
        version="Rev. 11.2025 (file dated 12/15/25)",
        files=("Federal Funds Checklist-121525 (2).docx",),
        url=None),
    "bus-29": dict(
        title="BFB-BUS-29: Management and Control of University Equipment",
        version="UC-FA-21-0555 (accessible)",
        files=("UC-FA-21-0555_BUS-29_ManagementControlUniversityEquipment_Accessible.pdf",),
        url=None),
    "regents-policy-5402": dict(
        title="Regents Policy 5402: Policy Generally Prohibiting Contracting for Services",
        version="Approved November 14, 2019; amended January 23, 2020",
        files=("Regents Policy 5402_ Policy Generally Prohibiting Contracting for Services _ Board of Regents.pdf",),
        url=None),
    "article-5-contracting-out": dict(
        title="AFSCME 3299 Article 5: Contracting Out",
        version="1-31-20",
        files=("article-5-contracting-out-1-31-20.pdf",),
        url=None),
    "post-employment-coi": dict(
        title="Summary of the Post-Employment Rules (UC Office of the General Counsel)",
        version="October 2023",
        files=("mm-postemployment-coi-rules-10-2023.pdf",),
        url=None),
    "bus-79": dict(
        title="BFB-BUS-79: Expenditures for Business Meetings, Entertainment, and Other Occasions",
        version="UC-FA-22-0617 (updated 12.15.2022, accessible)",
        files=("UC-FA-22-0617_BUS-79 Bus Meetings Entertainment_updated-accessible_12.15.2022.pdf",),
        url=None),
    "bus-2-alcohol": dict(
        title="BFB-BUS-2 / UCPS 120031: Tax-Free Alcohol Permits, Records, and Operations",
        version="Issued 6/30/2012",
        files=("UC-PS-12-0031_Tax-FreeAlcoholPermitsRecordsOperations (3).pdf",),
        url=None),
    "bus-63-risk-matrix": dict(
        title="UC BUS-63 Risk Matrix",
        version="Revised 9.19.2025",
        files=("BUS-63 Risk Matrix 9-19-2025.pdf",),
        url=None),
    "far-part-12": dict(
        title="FAR Part 12: Acquisition of Commercial Products and Commercial Services",
        version="48 CFR Ch. 1 (10-1-25 Edition)",
        files=("CFR-2025-title48-vol1-part12.pdf",),
        url="https://www.govinfo.gov/content/pkg/CFR-2025-title48-vol1/pdf/CFR-2025-title48-vol1-part12.pdf"),
    # not in the corpus: checked by hand, not by the quote test
    "far-2.101": dict(
        title="FAR 2.101 Definitions (inflation adjustment, 90 FR 41872)",
        version="effective October 1, 2025",
        files=(),
        url="https://www.acquisition.gov/far/2.101"),
}


@dataclass(frozen=True)
class Source:
    document_id: str
    page: Optional[int]
    section: str
    quote: str

    @property
    def document(self) -> dict:
        return DOCUMENTS[self.document_id]

    def cite(self) -> str:
        doc = self.document
        page = f", p.{self.page}" if self.page else ""
        return f"{doc['title']} ({doc['version']}){page}, {self.section}"

    def to_dict(self) -> dict:
        doc = self.document
        return {**asdict(self), "document": doc["title"], "version": doc["version"],
                "url": doc["url"], "verified_locally": bool(doc["files"])}


S = Source
SOURCES = {
    # competitive bidding
    "COMPETITIVE_BID_THRESHOLD": (
        S("bus-43", 9, "III, C. Expenditures of $100,000 or More Annually, 1. General Requirements",
          "requires that UC competitively bid all purchases with proposed annual expenditure of $100,000 or more "
          "unless an exception applies"),),
    "SIMPLIFIED_ACQUISITION_THRESHOLD": (
        S("far-2.101", None, "Simplified acquisition threshold",
          "Simplified acquisition threshold means $350,000"),),
    "FEDERAL_MICRO_PURCHASE": (
        S("far-2.101", None, "Micro-purchase threshold", "Micro-purchase threshold means $15,000"),),
    "CAMPUS_GRANT_MICRO_PURCHASE_MAX": (
        S("bus-43", 9, "III, B. Expenditure of Less Than $100,000 Annually, 4. Micro-purchase Award",
          "may establish a micro-purchase threshold of up to $50,000 in accordance with the OMB"),
        S("sspr-form", 1, "footnote *",
          "Campus locations may establish a micro-purchase threshold of up to $50,000 for grants and cooperative "
          "agreements"),),

    # small business / DVBE
    "SMALL_BUSINESS_LIMIT": (
        S("sspr-form", 1, "I. Source Selection, Non-Federal Funds",
          "Certified Small Business or DVBE (Only <$250k; Complete III, VII, VIII)"),
        # conflicts at exactly $250,000 - see SB_CEILING_CONFLICT_NOTE in thresholds.py
        S("bus-43", 25, "III, Part 3, C. Small Business First",
          "award purchase agreements valued up to $250,000 to a certified Small Business"),),
    "SMALL_BUSINESS_FEDERAL_SSPR_LIMIT": (
        S("sspr-form", 1, "I. Source Selection, Federal Funds",
          "Certified Small Business (Only <$100K; Complete III, VII, VIII)"),),
    "SMALL_BUSINESS_TWO_QUOTES_ABOVE": (
        S("bus-43", 25, "III, Part 3, C. Small Business First, 1. General Requirements (a)-(b)",
          "If the goods and/or services are valued greater than $100,000 but less than $250,000 annually, UC must "
          "obtain at least two (2) quotes"),),

    # SSPR form
    "SSPR_FEDERAL_CONTRACT": (S("sspr-form", 1, "header", "Federal Contract purchases ≥$15,000"),),
    "SSPR_FEDERAL_GRANT": (S("sspr-form", 1, "header", "Federal Grant/Cooperative Agreement purchases ≥$50,000"),),
    "SSPR_NON_FEDERAL": (S("sspr-form", 1, "header", "Non-Federal purchases ≥$100,000"),),
    "MIXED_FUNDING_FEDERAL_TRIGGERS": (
        S("sspr-form", 1, "I. Source Selection (Required)",
          "where the federal portion exceeds the above thresholds, check Federal side only"),),

    # federal
    "CERTIFIED_COST_PRICING_THRESHOLD": (
        S("sspr-form", 1, "III. Price Reasonableness, item 2",
          "Complete only for sole-sourced Federal non-commercial contract orders ≥ $2,500,000"),),
    "ANTI_LOBBYING_THRESHOLD": (
        S("federal-funds-checklist", None, "Required documentation table",
          "Anti-Lobby Verification ≥ $100,000"),),

    # split orders (a rule, not a dollar constant, but determinations cite it)
    "SPLIT_ORDER": (
        S("bus-43", 11, "Solicitation, a. Competition",
          "UC must not artificially divide requirements into separate transactions in order to avoid competition"),),

    # equipment (BUS-29)
    "EQUIPMENT_TAG_THRESHOLD": (
        S("bus-29", 3, "II. Definitions, Non-Inventorial Equipment",
          "NON-INVENTORIAL EQUIPMENT: Equipment which is non-expendable, tangible, personal property acquired for "
          "less than $5,000"),),
    "EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004": (
        S("bus-29", 2, "footnote 1", "Prior to July 1, 2004, the threshold was $1,500"),),

    # covered services
    "COVERED_SERVICES_PROHIBITION": (
        S("regents-policy-5402", 1, "Policy Summary",
          "There shall be a general prohibition on contracting out for services and functions that can be "
          "performed by University staff"),),
    "AFSCME_NOTICE_THRESHOLD": (
        S("article-5-contracting-out", 3, "D. Notice Provisions, 1",
          "The University shall provide notice to AFSCME 3299 prior to entering into, extending or renewing a "
          "contract that includes Covered Services valued at over $100,000"),),
    "WAGE_PARITY_MIN_DAYS": (
        S("regents-policy-5402", 3, "C. Employment Standards, 1. Wage and Benefits Parity",
          "Contracts for covered services exceeding $100,000 and ninety (90) days' duration shall include "
          "provisions requiring the contractor"),),

    # policy ladders (rules/policy_ladders.py) - no dollar constants, but every line is quoted
    "POST_EMPLOYMENT_TWO_YEAR": (
        S("post-employment-coi", 3, "3(a) Public Contract Code - Restrictions on Providing Goods or Services",
          "You are barred for two years from entering into a contract with the University to provide goods or "
          "services, if you engaged in any negotiations, planning, arrangements, or any part of the decision-making "
          "process related to the contract while still employed by the University."),),
    "POST_EMPLOYMENT_12_MONTH": (
        S("post-employment-coi", 3, "3(b) Public Contract Code - Restrictions on Providing Goods or Services",
          "You are barred for 12 months after leaving the University from entering into a contract with the "
          "University department you formerly worked for, if you were employed by that department in a policymaking "
          "position in the same general subject area as the proposed contract."),),
    "POST_EMPLOYMENT_RETIREE": (
        S("post-employment-coi", 3, "3(a)/3(b) note",
          "retirees are generally exempt from this ban and may nonetheless be hired back by the University"),),
    "POST_EMPLOYMENT_ONE_YEAR_REPRESENTING": (
        S("post-employment-coi", 3, "2. One Year Ban on Representing Other Parties Before the University",
          "You are barred for one year after leaving the University from appearing before or communicating with "
          "your campus while representing another person, in an attempt to influence certain University "
          "proceedings if you are being paid to do so."),),
    "BUS79_DOCUMENTATION": (
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "The completed request must include the following information:"),
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request", "Type of expense (lunch, dinner, etc.);"),
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request", "Type of event;"),),
    "BUS79_GUEST_LIST": (
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "Number of participants (attach a guest list containing the name and title of participants, and their "
          "occupation or group affiliation, in order to establish the business-related relationship to the "
          "University)"),),
    "BUS79_PURPOSE": (
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "Date and location of the event;"),
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "Business-related nature of the occasion or purpose of the event; and"),
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "The signature, printed name, and department of the department head or approving authority."),),
    "BUS79_RECEIPTS": (
        S("bus-79", 17, "IV.B.1 Reimbursement or Payment Request",
          "Expenses of $75 or more per occasion must be supported by original itemized receipts"),),
    "ALCOHOL_TTB_APPLICATION": (
        S("bus-2-alcohol", 2, "III.A Securing Industrial Use Permits",
          "Applications for industrial use permits for tax-free alcohol are filed with the Alcohol and Tobacco Tax "
          "and Trade Bureau of the U.S. Department of the Treasury"),),
    "ALCOHOL_REGENTS_NAME": (
        S("bus-2-alcohol", 2, "III.A Securing Industrial Use Permits",
          'All tax-free alcohol use applications are to be made in the name of "The Regents of the University of '
          'California."'),),
    "ALCOHOL_TTB_PERMIT": (
        S("bus-2-alcohol", 2, "III.B Approval by TTB", "TTB will issue an official numbered"),),
    "ALCOHOL_PERMIT_CONTINUOUS": (
        S("bus-2-alcohol", 2, "III.B Approval by TTB",
          "Permits are continuous unless automatically terminated by the terms of the permit."),),
    "ALCOHOL_VENDOR_PERMIT_ON_FILE": (
        S("bus-2-alcohol", 3, "III.C.1 Purchasing Requirements",
          "Shipments may not be made until the vendor has a signed copy of a valid permit on file"),),
    "ALCOHOL_SEMIANNUAL_INVENTORY": (
        S("bus-2-alcohol", 6, "5. Inventories",
          "a physical inventory of tax-free alcohol shall be taken semiannually or at other inventory periods "
          "approximately six months apart"),),
    "ALCOHOL_RECORDS": (
        S("bus-2-alcohol", 5, "2. Conditions of Use of Tax-Free Alcohol",
          "shall sign a receipt for each delivery and shall maintain complete, accurate, and up-to-date records of "
          "all tax-free alcohol received and issued"),),
    "ALCOHOL_PREMISES_ONLY": (
        S("bus-2-alcohol", 3, "III.C.2 Conditions of Use", "shall be used only on the premises of the University"),),
    "RISK_MATRIX_HIGH_COI": (
        S("bus-63-risk-matrix", 1, "How to Use",
          "If the contract involves any one of the Risk Exposures C-K, the entire contract is classified as "
          "presenting High risk and a COI must be collected."),
        S("bus-63-risk-matrix", 2, "High Risk", "Collection of a Certificate of Insurance (COI) is required."),),
    "RISK_MATRIX_LOW_MODERATE_COI": (
        S("bus-63-risk-matrix", 2, "Low Risk / Moderate Risk",
          "A Certificate of Insurance (COI) does not need to be collected; the agreement or PO should require the "
          "Contractor/External Party to provide a COI to UC upon UC"),),
}
del S

# reference-fact topics -> the constants they quote
TOPIC_SOURCES = {
    "bid": ["COMPETITIVE_BID_THRESHOLD", "SIMPLIFIED_ACQUISITION_THRESHOLD"],
    "sspr": ["SSPR_FEDERAL_CONTRACT", "SSPR_FEDERAL_GRANT", "SSPR_NON_FEDERAL"],
    "federal": ["FEDERAL_MICRO_PURCHASE", "CAMPUS_GRANT_MICRO_PURCHASE_MAX", "SIMPLIFIED_ACQUISITION_THRESHOLD",
                "ANTI_LOBBYING_THRESHOLD"],
    "mixed": ["MIXED_FUNDING_FEDERAL_TRIGGERS"],
    "multi_year": ["COMPETITIVE_BID_THRESHOLD"],
    "small_business": ["SMALL_BUSINESS_LIMIT", "SMALL_BUSINESS_TWO_QUOTES_ABOVE", "SMALL_BUSINESS_FEDERAL_SSPR_LIMIT"],
    "sole_source": ["CERTIFIED_COST_PRICING_THRESHOLD"],
    "split": ["SPLIT_ORDER"],
    "equipment": ["EQUIPMENT_TAG_THRESHOLD", "EQUIPMENT_TAG_THRESHOLD_PRE_JULY_2004"],
    "micro": ["FEDERAL_MICRO_PURCHASE", "CAMPUS_GRANT_MICRO_PURCHASE_MAX"],
    "sat": ["SIMPLIFIED_ACQUISITION_THRESHOLD", "COMPETITIVE_BID_THRESHOLD"],
    "covered": ["COVERED_SERVICES_PROHIBITION", "AFSCME_NOTICE_THRESHOLD", "WAGE_PARITY_MIN_DAYS"],
}


def sources_for(keys) -> list:
    # unique Source records for constant names, in first-seen order
    seen, out = set(), []
    for key in keys:
        for src in SOURCES[key]:
            if src not in seen:
                seen.add(src)
                out.append(src)
    return out
