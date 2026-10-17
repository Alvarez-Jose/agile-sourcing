# evaluation/benchmarks/validation/build_review_request.py
# builds the Procurement review request: 25 policy-interpretation questions, each with a
# statement of facts, the question presented and the provision at issue quoted from the
# document, with blank response fields for the reviewer. written the way a request for
# policy interpretation to a general counsel's office is written; nothing in it is drafted
# by the system under evaluation.
#
#   python evaluation/benchmarks/validation/build_review_request.py
#   -> Procurement_Policy_Review_Request_2026-10.xlsx and review_questions.json next to this file

import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
TODAY = date(2026, 10, 17)

DOCUMENTS = [
    ("BUS-43", "BFB-BUS-43, Purchases of Goods and Services; Supply Chain Management", "Interim policy, issued and effective January 26, 2026", "BUS-43_Interim_2026-01-26.pdf"),
    ("SSPR", "Source Selection & Price Reasonableness Justification Form (SSPR)", "Revised 12-2025 (UCSC Financial Affairs)", "SSPR_Official_UCSC_2025-12.pdf"),
    ("SSPR FAQ", "Source Selection & Price Reasonableness FAQ", "Undated (references the 2021 thresholds)", "sspr-faq.pdf"),
    ("OGC", "Summary of the Post-Employment Rules, Office of the General Counsel", "October 2023", "mm-postemployment-coi-rules-10-2023.pdf"),
    ("RP 5402", "Regents Policy 5402: Policy Generally Prohibiting Contracting for Services", "Approved November 14, 2019; amended January 23, 2020", "Regents Policy 5402_ Policy Generally Prohibiting Contracting for Services _ Board of Regents.pdf"),
    ("Art. 5", "AFSCME 3299 Agreement, Article 5, Contracting Out", "January 31, 2020", "article-5-contracting-out-1-31-20.pdf"),
    ("BUS-29", "BFB-BUS-29, Management and Control of University Equipment", "UC-FA-21-0555 (accessible edition)", "UC-FA-21-0555_BUS-29_ManagementControlUniversityEquipment_Accessible.pdf"),
    ("BUS-79", "BFB-BUS-79, Expenditures for Business Meetings, Entertainment, and Other Occasions", "Updated December 15, 2022", "UC-FA-22-0617_BUS-79 Bus Meetings Entertainment_updated-accessible_12.15.2022.pdf"),
    ("BUS-2", "BFB-BUS-2 (UCPS 120031), Tax-Free Alcohol Permits, Records, and Operations", "Issued June 30, 2012", "UC-PS-12-0031_Tax-FreeAlcoholPermitsRecordsOperations (3).pdf"),
    ("Risk Matrix", "UC BUS-63 Risk Matrix", "Revised September 19, 2025", "BUS-63 Risk Matrix 9-19-2025.pdf"),
    ("T&C", "University of California Terms and Conditions of Purchase", "April 1, 2025", "UC Terms and Conditions-04-01-25.pdf"),
    ("BAA", "Appendix - Business Associate Agreement", "Current UC template", "appendix-baa.pdf"),
    ("App. DS", "Appendix - Data Security", "Current UC template", "appendix-data-security.pdf"),
    ("IC Guidelines", "UC Independent Contractor Guidelines for Federal Tax Purposes", "GU-FA-20-0506 (accessible edition)", "GU-FA-20-0506_UCIndependentContractorGuidelines_Accessible.pdf"),
    ("G-41", "BFB-G-41, Employee Non-Cash Awards and Other Gifts", "UC-FA-23-672 (accessible edition)", "UC-FA-23-672_BFB-G-41_EmployeeNon-CashAwardGifts_Accessible.pdf"),
    ("G-13", "BFB-G-13, Policy and Regulations Governing Moving and Relocation", "April 12, 2018", "UC-FA-18-0381_BFB-G-13_MovingRelocationPolicy_Accessible_4.12.2018.pdf"),
    ("FFC", "UC Procurement Federal Funds Checklist", "Rev. 11.2025 (file dated December 15, 2025)", "Federal Funds Checklist-121525 (2).docx"),
]

# (subject, facts, question presented, [(provision quote, citation), ...])
QUESTIONS = [
    ("Competitive bidding; aggregation of orders",
     "A department anticipates purchasing laboratory consumables from a single supplier under a series of "
     "purchase orders during the fiscal year. Each order is expected to fall between $20,000 and $30,000. "
     "Aggregate expenditure with the supplier for the year is projected at approximately $140,000. No "
     "strategically sourced agreement covers the items.",
     "Whether the requirement to competitively bid is determined by the aggregate annual expenditure with the "
     "supplier rather than by the value of each order, and whether the department may continue to issue "
     "individual orders without a competitive solicitation.",
     [("California Public Contract Code Section 10507 et seq. requires that UC competitively bid all purchases "
       "with proposed annual expenditure of $100,000 or more unless an exception applies.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III.C.1, p. 9"),
      ("UC must not artificially divide requirements into separate transactions in order to avoid competition.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III.D.1.a, p. 11")]),

    ("Small Business First; federally funded purchase",
     "A department proposes to purchase an instrument at a cost of $180,000, funded entirely by a National "
     "Science Foundation grant. A certified small business is able to supply the instrument, and the "
     "department has obtained one quotation from it.",
     "Whether the Small Business First provisions permit award to the certified small business without a "
     "competitive solicitation at this value, and whether the federal source of funds alters the number of "
     "quotations required or the sections of the SSPR to be completed.",
     [("California Public Contract Code Section 10508.5 allows UC to limit competition and award purchase "
       "agreements valued up to $250,000 to a certified Small Business (SB) or Disabled Veteran Business "
       "Enterprise (DVBE) without being competitively bid, so long as the UC obtains price quotations from two "
       "or more certified SBs, or two or more certified DVBEs.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III, Part 3, C (Small Business First), p. 25"),
      ("Federal Funds: ... Certified Small Business (Only <$100K; Complete III, VII, VIII)",
       "SSPR Form (Rev. 12-2025), Section I, Source Selection, p. 1")]),

    ("Mixed funding; SSPR federal threshold",
     "A department proposes a purchase of $120,000, of which $50,000 is charged to a federal grant and "
     "$70,000 to departmental funds.",
     "Whether the federal portion of the purchase meets the SSPR threshold for federally funded grant "
     "purchases such that the federal requirements apply to the entire transaction, and which side of the "
     "SSPR form is to be completed.",
     [("This document must be completed by the requesting Department for federally funded contract purchases "
       ">= $15,000 (including tax and shipping), federally funded grant/cooperative agreement purchases >= $50,000 "
       "(including tax and shipping), and non-federally funded purchases >= $100,000 (excluding tax but "
       "including shipping).",
       "SSPR Form (Rev. 12-2025), header, p. 1"),
      ("For mixed funding where the federal portion exceeds the above thresholds, check Federal side only.",
       "SSPR Form (Rev. 12-2025), Section I, Source Selection, p. 1")]),

    ("Mixed funding; status of the SSPR FAQ",
     "The SSPR FAQ states that where the federal portion of a mixed-funded transaction exceeds $10,000, federal "
     "requirements apply to the whole transaction. The current SSPR form (Rev. 12-2025) instructs that for "
     "mixed funding the federal side is to be completed where the federal portion exceeds the thresholds "
     "stated on the form ($15,000 for contracts; $50,000 for grants and cooperative agreements).",
     "Whether the $10,000 federal-portion rule stated in the FAQ remains operative, or has been superseded by "
     "the thresholds stated on the Rev. 12-2025 form.",
     [("But, if the Federal funds portion is over the $10,000 threshold, you must adhere to Federal requirements "
       "for the whole transaction.",
       "SSPR FAQ, 'How do these thresholds apply to mixed funding?', p. 1"),
      ("For mixed funding where the federal portion exceeds the above thresholds, check Federal side only.",
       "SSPR Form (Rev. 12-2025), Section I, Source Selection, p. 1")]),

    ("Former employee; participation in supplier selection",
     "An employee who served on the evaluation committee for a software request for proposals separated from "
     "the University eight months ago and has since formed a consulting firm. The department that issued the "
     "RFP proposes to engage the firm to implement the software selected under it. The engagement would be "
     "funded from a private gift.",
     "Whether the University may contract with the former employee's firm, and whether the source of funds "
     "bears on the answer.",
     [("UC may not purchase, lease goods from, or contract for services with, any former employee (including "
       "those who had teaching or research responsibilities) if any of the following apply: The former employee "
       "left UC less than two years ago, and the former employee, while at UC, participated in the "
       "decision-making process relevant to selecting the supplier. This includes engaging in negotiations, "
       "making procurement transactions, or planning for purchases.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III.F.2.b (Former Employee), p. 28"),
      ("You are barred for two years from entering into a contract with the University to provide goods or "
       "services, if you engaged in any negotiations, planning, arrangements, or any part of the decision-making "
       "process related to the contract while still employed by the University.",
       "OGC, Summary of the Post-Employment Rules (Oct. 2023), item 3(a), p. 3")]),

    ("Former employee; policy-making position; retiree",
     "A department director retired from the University six months ago. Her former department proposes to "
     "retain her as an independent contractor to advise on a procurement in the subject area she managed while "
     "employed. She had no involvement in planning the procurement before her retirement.",
     "Whether the twelve-month restriction applicable to former employees who held policy-making "
     "responsibilities applies to a retiree, and how the retiree exemption described in the Office of the "
     "General Counsel summary is to be reconciled with BUS-43 Part III.F.2.b.",
     [("The former employee left UC less than one year (12 months) ago, and the former employee had policy-making "
       "responsibilities for the same general subject area as the proposed agreement while at UC.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III.F.2.b (Former Employee), p. 28"),
      ("You are barred for 12 months after leaving the University from entering into a contract with the "
       "University department you formerly worked for, if you were employed by that department in a policymaking "
       "position in the same general subject area as the proposed contract. Note: retirees are generally exempt "
       "from this ban and may nonetheless be hired back by the University.",
       "OGC, Summary of the Post-Employment Rules (Oct. 2023), item 3(b), p. 3")]),

    ("Former employee; asserted one-year contracting ban",
     "A department states that a former employee 'is subject to a one-year contract ban' and asks whether it "
     "may engage him as an independent contractor, for a project funded by a federal award, once the year has "
     "elapsed. The department has not identified the former employee's role or the date of separation.",
     "Whether University policy imposes a one-year ban on contracting with former employees as described, and "
     "if not, which post-employment restrictions govern the proposed engagement and what facts are required to "
     "apply them.",
     [("You are barred for one year after leaving the University from appearing before or communicating with "
       "your campus while representing another person, in an attempt to influence certain University proceedings "
       "if you are being paid to do so.",
       "OGC, Summary of the Post-Employment Rules (Oct. 2023), item 2, p. 3"),
      ("You are barred for two years from entering into a contract with the University to provide goods or "
       "services, if you engaged in any negotiations, planning, arrangements, or any part of the decision-making "
       "process related to the contract while still employed by the University.",
       "OGC, Summary of the Post-Employment Rules (Oct. 2023), item 3(a), p. 3")]),

    ("Contracting out; covered services; new facility",
     "A campus unit proposes a three-year contract, valued at $450,000, with an outside firm to provide "
     "custodial services in a newly acquired building. No University custodial staff are presently assigned to "
     "the building, and the unit represents that no University position would be eliminated.",
     "Whether the proposed contract is permitted under Regents Policy 5402; whether advance notice to AFSCME "
     "3299 is required; and whether the wage and benefit parity provisions apply to the contract.",
     [("There shall be a general prohibition on contracting out for services and functions that can be performed "
       "by University staff. ... The University shall prioritize the use of its employees to perform functions "
       "and services whenever possible and the use of outside contractors will not cause or facilitate the "
       "displacement of University employees.",
       "Regents Policy 5402 (amended Jan. 23, 2020), Policy Summary, p. 1"),
      ("The University shall provide notice to AFSCME 3299 prior to entering into, extending or renewing a "
       "contract that includes Covered Services valued at over $100,000.",
       "AFSCME 3299 Article 5 (Jan. 31, 2020), Section D.1, p. 3"),
      ("Contracts for covered services exceeding $100,000 and ninety (90) days' duration shall include provisions "
       "requiring the contractor",
       "Regents Policy 5402, Section C.1 (Wage and Benefits Parity), p. 3")]),

    ("Contracting out; temporary absence of staff",
     "A clinical department proposes to contract for medical imaging technician services for six months, at a "
     "cost of $90,000, while two University technicians are on approved leave.",
     "Whether the temporary absence of University staff is a recognized basis for contracting out a covered "
     "service, and whether notice to AFSCME 3299 is required at the stated value.",
     [("medical imaging or other medical technician services. These shall be referred to as \"covered services\" "
       "for purposes of this policy. The University will utilize its employees to perform covered services that "
       "have been customarily performed by University employees to the greatest extent possible before resorting "
       "to the use of private contractors to provide such services.",
       "Regents Policy 5402 (amended Jan. 23, 2020), Policy Text, p. 2"),
      ("The University shall provide notice to AFSCME 3299 prior to entering into, extending or renewing a "
       "contract that includes Covered Services valued at over $100,000.",
       "AFSCME 3299 Article 5 (Jan. 31, 2020), Section D.1, p. 3")]),

    ("Equipment; inventorial threshold; subsequent accessory",
     "A department purchased a microscope in March at a cost of $4,800. In June it purchased an objective lens "
     "for the same microscope at a cost of $1,400. The combined cost is $6,200.",
     "Whether the microscope, the lens, or the combined asset must be inventoried and tagged under BUS-29.",
     [("NON-INVENTORIAL EQUIPMENT: Equipment which is non-expendable, tangible, personal property acquired for "
       "less than $5,000, which is freestanding, complete in itself, does not lose its identity when affixed to or "
       "installed in other property, and which has a normal life expectancy of more than one year.",
       "BUS-29 (UC-FA-21-0555), Part II, Definitions, p. 3")]),

    ("Sole source; brand preference",
     "A principal investigator requests sole-source award of a $140,000 purchase of a sequencing instrument of "
     "a particular manufacturer, on the ground that the laboratory's protocols were developed on that "
     "manufacturer's platform. Two other manufacturers offer instruments meeting the stated technical "
     "specifications.",
     "Whether the stated ground constitutes a permissible sole source justification, and if not, what "
     "procurement method is required at this value.",
     [("Sole Source Goods and/or Services: Sole source goods and/or services are the only ones that will meet "
       "UC's needs because they are: a) unique; b) available from only one source; or c) are designed to match "
       "others used in or furnished to a particular/installation, facility, or location. See SSPR Form for "
       "detailed definitions.",
       "BUS-43 (Interim, Jan. 26, 2026), Part II, Definitions, p. 6")]),

    ("Emergency purchase; exception to competitive bidding",
     "A water main failure has flooded a research laboratory. The department requires a restoration contractor "
     "immediately. The estimated cost is $160,000.",
     "Whether an emergency exception to the competitive bidding requirement is available; by whom it may be "
     "granted; and what the department must document.",
     [("Exceptions: The P/SCD may grant exceptions as to dollar amount and items to be purchased when notified by "
       "the responsible official that an emergency situation exists. The exception must be on a transaction by "
       "transaction basis.",
       "BUS-43 (Interim, Jan. 26, 2026), Part III.I.4, p. 22")]),

    ("Business meals; required documentation",
     "A department submits an Entertainment Check Request for a working lunch held with a visiting academic "
     "delegation. The request states the date, the name of the restaurant and the total charged, and attaches "
     "an itemized receipt for $412. No other information is provided.",
     "Whether the request is complete for purposes of BUS-79, and if not, what information must be supplied "
     "before it may be approved.",
     [("The completed request must include the following information: Type of expense (lunch, dinner, etc.); "
       "Type of event; Number of participants (attach a guest list containing the name and title of participants, "
       "and their occupation or group affiliation, in order to establish the business-related relationship to the "
       "University); Date and location of the event; Business-related nature of the occasion or purpose of the "
       "event; and The signature, printed name, and department of the department head or approving authority.",
       "BUS-79 (updated Dec. 15, 2022), Part IV.B.1, p. 17")]),

    ("Tax-free alcohol; asserted authority of a DEA registration",
     "A laboratory holds a Drug Enforcement Administration registration for controlled substances. It asks to "
     "purchase 200-proof ethanol free of tax 'under its DEA registration.'",
     "Whether a DEA registration authorizes the purchase of tax-free alcohol, and what authorization is in fact "
     "required before a supplier may ship.",
     [("Applications for industrial use permits for tax-free alcohol are filed with the Alcohol and Tobacco Tax "
       "and Trade Bureau of the U.S. Department of the Treasury. All tax-free alcohol use applications are to be "
       "made in the name of \"The Regents of the University of California.\"",
       "BUS-2 / UCPS 120031 (June 30, 2012), Part III.A, p. 2"),
      ("Shipments may not be made until the vendor has a signed copy of a valid permit on file.",
       "BUS-2 / UCPS 120031 (June 30, 2012), Part III.C.1, p. 3")]),

    ("Tax-free alcohol; physical inventory",
     "A department last took a physical inventory of its tax-free alcohol nine months ago. It proposes to "
     "withdraw additional alcohol from inventory this week.",
     "Whether the department is in compliance with the inventory requirement, and whether withdrawals may be "
     "made before a physical inventory is taken.",
     [("As required by federal law, a physical inventory of tax-free alcohol shall be taken semiannually or at "
       "other inventory periods approximately six months apart.",
       "BUS-2 / UCPS 120031 (June 30, 2012), Part III.C.5, p. 6")]),

    ("Certificate of insurance; moderate digital risk",
     "A software-as-a-service supplier will host departmental scheduling data classified at Protection Level "
     "P2. The engagement presents no other risk exposure identified in the Risk Matrix.",
     "Whether a certificate of insurance must be collected from the supplier, and what the agreement must "
     "provide with respect to insurance.",
     [("If the contract involves any one of the Risk Exposures C-K, the entire contract is classified as "
       "presenting High risk and a COI must be collected.",
       "UC BUS-63 Risk Matrix (rev. Sept. 19, 2025), How to Use, p. 1"),
      ("Moderate Risk: A Certificate of Insurance (COI) does not need to be collected; the agreement or PO should "
       "require the Contractor/External Party to provide a COI to UC upon UC's request.",
       "UC BUS-63 Risk Matrix (rev. Sept. 19, 2025), p. 2")]),

    ("Certificate of insurance; transportation of students",
     "A charter bus company will transport University students to a field site under a contract valued at "
     "$18,000.",
     "Whether a certificate of insurance must be collected notwithstanding the contract value, and what minimum "
     "automobile liability limits apply.",
     [("If the contract involves any one of the Risk Exposures C-K, the entire contract is classified as "
       "presenting High risk and a COI must be collected.",
       "UC BUS-63 Risk Matrix (rev. Sept. 19, 2025), How to Use, p. 1 (Exposure K, Transportation)"),
      ("Business Automobile Liability Insurance for owned, scheduled, non-owned, or hired automobiles with a "
       "combined single limit of not less than one million dollars ($1,000,000) per occurrence. (Required only if "
       "Supplier drives on UC premises or transports UC employees, officers, invitees, or agents",
       "UC Terms and Conditions of Purchase (Apr. 1, 2025), Article on Insurance, p. 8")]),

    ("General liability limits; asserted dependence on contract value",
     "A caterer engaged for a department reception carries commercial general liability insurance with a "
     "per-occurrence limit of $500,000. The department takes the position that a lower limit is acceptable "
     "because the contract value is under $10,000.",
     "Whether the minimum general liability limits in the UC Terms and Conditions vary with the value of the "
     "contract, and whether the department may proceed with the caterer as insured.",
     [("Commercial Form General Liability Insurance. (contractual liability included) with limits as follows: "
       "(i) Each Occurrence $ 1,000,000 (ii) Products/Completed Operations Aggregate $ 2,000,000 (iii) Personal "
       "and Advertising Injury $ 1,000,000 (iv) General Aggregate $ 2,000,000",
       "UC Terms and Conditions of Purchase (Apr. 1, 2025), Article on Insurance, p. 8")]),

    ("Protected health information; institutional data; applicable appendices",
     "A vendor will analyze de-identified patient records for a research study and, in the course of the "
     "engagement, will also be given access to the department's internal file server, which holds "
     "administrative records.",
     "Whether a Business Associate Agreement is required; whether the Appendix - Data Security is required; "
     "and whether both may apply to a single engagement.",
     [("Services that involve receiving, creating, maintaining and/or transmitting Protected Health Information "
       "(PHI) of UC as a Business Associate of UC as defined under 45 C.F.R. 160.103.",
       "Appendix - Business Associate Agreement, Recital B, p. 1"),
      ("The purpose of this Appendix-Data Security is to specify Supplier's cybersecurity and risk management "
       "responsibilities when Supplier has access to Institutional Information and/or IT Resources.",
       "Appendix - Data Security, Article 1.A, p. 1")]),

    ("Worker classification; recently separated employee",
     "A department proposes to pay an employee who separated from the University last month as an independent "
     "contractor to perform the same duties, on the same schedule, using University equipment and workspace.",
     "Whether the worker may be classified as an independent contractor under the Internal Revenue Service "
     "common law standards summarized in the Guidelines, and what the consequence of misclassification is.",
     [("The purpose of this Guideline is to provide a summary of the criteria used to determine a worker's status "
       "under Internal Revenue Service (IRS) common law standards and details the penalties imposed by the IRS for "
       "the misclassification of workers as independent contractors.",
       "UC Independent Contractor Guidelines for Federal Tax Purposes (GU-FA-20-0506), Part I, Summary, p. 1")]),

    ("Employee gifts; per-person limit",
     "A department proposes to give a $150 gift card to each of five employees in recognition of the completion "
     "of a project.",
     "Whether the proposed gifts exceed the per-person limit for employee recognition awards, and what the tax "
     "treatment is if the limit is exceeded.",
     [("Employee Recognition (including Spot Awards) $75 ... Length of Service $400 ... Retirement $400 ... "
       "Sympathy Gift Tangible Personal Property $75 ... Prizes and Other Gifts $75",
       "G-41 (UC-FA-23-672), table of Award or Gift Type / Per-Person Limit, p. 2")]),

    ("Moving and relocation; current employee transferring between locations",
     "A current employee in a Professional and Support Staff position transfers from another University "
     "location to UC Santa Cruz. The hiring department states that moving expense reimbursement is available "
     "only to newly hired employees.",
     "Whether a current employee who transfers to a new University location is eligible for reimbursement of "
     "moving expenses under G-13.",
     [("Moving expenses eligible for payment are defined in Internal Revenue Code (I.R.C.) Section 217(b)(1) as "
       "the reasonable costs (or expenses) incurred by a new appointee, or by a current employee who transfers to "
       "a new University location, of moving household goods and personal effects to a new residence.",
       "G-13 (Apr. 12, 2018), Part II, Definitions, Moving Expenses, p. 2")]),

    ("Federal contract funds; FAR Part 12 commercial items",
     "A department proposes to purchase commercial off-the-shelf software with funds from a federal contract. "
     "It asks which Federal Acquisition Regulation Part 12 (commercial items) requirements must be flowed down "
     "to the supplier.",
     "Whether University policy or the UC Terms and Conditions specify FAR Part 12 requirements for purchases "
     "under federal contracts, or whether the applicable clauses are to be determined from the prime contract. "
     "If the question is not addressed by policy, please so state.",
     [("Article 11.8 Debarment, Suspension, U.S. Government Restricted Party Lists; Article 11.10 Covered "
       "Telecommunications Equipment; Article 8.1(c)(i) Rights to Inventions; Article 8.1(c)(ii) Clean Air Act; "
       "Article 8.1(c)(iii) Byrd Anti-Lobbying; Article 8.1(c)(iv) Procurement of Recovered Materials; Article "
       "8.1(c)(v) Domestic Preferences for Procurements; Article 11.9 Equal Opportunity",
       "UC Procurement Federal Funds Checklist (Rev. 11.2025), required flow-down articles table")]),

    ("Use of another public agency's competitively awarded contract",
     "A department proposes to purchase fleet vehicles through a contract competitively awarded by another "
     "California public agency, under a cooperative purchasing provision in that contract, rather than through "
     "a University solicitation.",
     "Whether BUS-43 permits the University to rely on another public agency's competitive award in lieu of its "
     "own solicitation, and under what conditions. If the question is not addressed by policy, please so state.",
     [("Strategically Sourced Agreements: Agreements designated for the supply of goods and/or services to UC "
       "that were awarded as a result of a competitive bid process or negotiation.",
       "BUS-43 (Interim, Jan. 26, 2026), Part II, Definitions, p. 6")]),

    ("SSPR processing time",
     "A department submits an SSPR form for a $75,000 purchase funded by a federal grant and asks how many "
     "business days Procurement Services requires to review it.",
     "Whether University policy prescribes a time within which an SSPR must be reviewed. If the question is a "
     "matter of office practice rather than policy, please so state and indicate the current practice.",
     [("This document must be completed by the requesting Department for ... federally funded grant/cooperative "
       "agreement purchases >= $50,000 (including tax and shipping)",
       "SSPR Form (Rev. 12-2025), header, p. 1")]),
]
assert len(QUESTIONS) == 25, len(QUESTIONS)

FONT = "Times New Roman"
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC")
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
EXAMPLE_FILL = PatternFill("solid", fgColor="EDEDED")
WRAP = Alignment(wrap_text=True, vertical="top")


def cell(ws, ref, value, bold=False, size=11, italic=False, fill=None, align=WRAP, border=True, color=None):
    c = ws[ref]
    c.value = value
    c.font = Font(name=FONT, size=size, bold=bold, italic=italic, color=color)
    c.alignment = align
    if fill:
        c.fill = fill
    if border:
        c.border = BORDER
    return c


def cover(wb):
    ws = wb.active
    ws.title = "Memorandum"
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 95
    ws.sheet_view.showGridLines = False
    r = 1
    cell(ws, f"A{r}", "MEMORANDUM", bold=True, size=14, border=False); r += 2
    for label, val in [("TO:", "Procurement Services, UC Santa Cruz"),
                       ("FROM:", "Agile Sourcing project team"),
                       ("DATE:", TODAY.strftime("%B %d, %Y")),
                       ("RE:", "Request for review of twenty-five policy-interpretation questions")]:
        cell(ws, f"A{r}", label, bold=True, border=False); cell(ws, f"B{r}", val, border=False); r += 1
    r += 1
    paras = [
        "1. Purpose. The attached schedule sets out twenty-five questions of the kind the project team expects "
        "departments to put to Procurement Services. Each question is accompanied by a short statement of facts "
        "and by the provision of University policy that appears to govern it, quoted from the current document "
        "and cited to the page. We ask that Procurement Services record its response to each question. The "
        "responses will serve as the reference against which the project's policy assistant is measured; no "
        "response will be used for any other purpose without your agreement.",
        "2. What is requested. For each question, please complete the three shaded columns on the 'Questions' "
        "sheet: (a) Response - the answer in your own words, in one to three sentences, stating the conclusion "
        "and the condition on which it depends; (b) Authority - the provision relied on, if different from or in "
        "addition to the provision quoted; and (c) Frequency - how often departments raise the question in "
        "practice. Initials and date in the final column are optional but helpful.",
        "3. Questions that policy does not answer. Several questions are included because we expect that policy "
        "does not resolve them. Where that is so, please state 'Not addressed by policy' in the Response column "
        "and, if you are able, describe the current practice of the office. A response of that kind is as "
        "useful to us as a substantive answer.",
        "4. Quoted provisions. The provisions quoted were taken from the documents listed on the 'Documents' "
        "sheet, in the versions stated there. If a quoted provision is superseded, or if a different provision "
        "controls, please say so in the Authority column; we would rather learn that the schedule is wrong than "
        "measure against it.",
        "5. Time required. We estimate that the schedule can be completed in about one hour. Questions 4, 7 and "
        "23 through 25 are the ones on which we most need the judgment of a senior buyer.",
        "6. Return. Please return the completed workbook to the project team. A row illustrating the expected "
        "form of a response appears in grey at the top of the 'Questions' sheet and may be disregarded.",
    ]
    for p in paras:
        ws.merge_cells(f"A{r}:B{r}")
        c = cell(ws, f"A{r}", p, border=False)
        ws.row_dimensions[r].height = 15 * (len(p) // 110 + 2)
        r += 1
    ws.print_options.horizontalCentered = True


def documents(wb):
    ws = wb.create_sheet("Documents")
    ws.sheet_view.showGridLines = False
    widths = [12, 64, 44, 60]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for i, h in enumerate(["Short form", "Document", "Version reviewed", "File"], 1):
        cell(ws, f"{get_column_letter(i)}1", h, bold=True, fill=HEAD_FILL, color="FFFFFF")
    for r, (short, title, version, fname) in enumerate(DOCUMENTS, 2):
        for i, v in enumerate([short, title, version, fname], 1):
            cell(ws, f"{get_column_letter(i)}{r}", v)
    ws.freeze_panes = "A2"


def questions(wb):
    ws = wb.create_sheet("Questions")
    ws.sheet_view.showGridLines = False
    headers = ["No.", "Subject", "Statement of facts", "Question presented", "Provision at issue (quoted)",
               "Source (document, version, page)", "Response", "Authority relied on", "Frequency of inquiry",
               "Reviewer initials / date"]
    widths = [6, 26, 60, 52, 64, 34, 52, 34, 18, 16]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        col = get_column_letter(i)
        ws.column_dimensions[col].width = w
        cell(ws, f"{col}1", h, bold=True, fill=HEAD_FILL, color="FFFFFF")
    ws.row_dimensions[1].height = 32

    # example row, to be disregarded by the reviewer
    example = ["Ex.", "Example (disregard)",
               "A department proposes a $60,000 purchase of furniture from departmental funds.",
               "Whether the purchase must be competitively bid.",
               "California Public Contract Code Section 10507 et seq. requires that UC competitively bid all "
               "purchases with proposed annual expenditure of $100,000 or more unless an exception applies.",
               "BUS-43 (Interim, Jan. 26, 2026), Part III.C.1, p. 9",
               "No. The purchase is below the $100,000 annual threshold; competitive bidding is not required, "
               "although competition is encouraged. The department should confirm that no related orders bring "
               "the annual total with the supplier to $100,000 or more.",
               "BUS-43 Part III.B (purchases under $100,000); SSPR Form, header.",
               "Frequently", "A.B. 10/20/2026"]
    for i, v in enumerate(example, 1):
        cell(ws, f"{get_column_letter(i)}2", v, italic=True, fill=EXAMPLE_FILL)
    ws.row_dimensions[2].height = 110

    dv = DataValidation(type="list", formula1='"Rarely,Occasionally,Frequently,Never seen"', allow_blank=True)
    ws.add_data_validation(dv)
    rows = []
    for n, (subject, facts, q, provisions) in enumerate(QUESTIONS, 1):
        r = n + 2
        quote = "\n\n".join(f'"{p}"' for p, _ in provisions)
        source = "\n\n".join(c for _, c in provisions)
        values = [n, subject, facts, q, quote, source, "", "", "", ""]
        for i, v in enumerate(values, 1):
            fill = INPUT_FILL if i in (7, 8, 9, 10) else None
            cell(ws, f"{get_column_letter(i)}{r}", v, fill=fill)
        dv.add(f"I{r}")
        longest = max(len(facts), len(q), len(quote) * 0.85)
        ws.row_dimensions[r].height = max(90, min(400, 15 * (longest // 55 + 2)))
        rows.append({"no": n, "subject": subject, "facts": facts, "question": q,
                     "provisions": [{"quote": p, "cite": c} for p, c in provisions]})
    ws.freeze_panes = "C2"
    ws.print_title_rows = "1:1"
    legend_row = len(QUESTIONS) + 4
    cell(ws, f"A{legend_row}", "Shaded columns (Response, Authority relied on, Frequency of inquiry, Reviewer) "
                               "are for completion by Procurement Services. All other columns are fixed.",
         italic=True, border=False)
    ws.merge_cells(f"A{legend_row}:J{legend_row}")
    return rows


def main():
    wb = Workbook()
    cover(wb)
    documents(wb)
    rows = questions(wb)
    out = HERE / "Procurement_Policy_Review_Request_2026-10.xlsx"
    wb.save(out)
    json.dump({"prepared": TODAY.isoformat(), "questions": rows},
              open(HERE / "review_questions.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"wrote {out} and review_questions.json ({len(rows)} questions)")


if __name__ == "__main__":
    main()
