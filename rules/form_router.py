# rules/form_router.py
# which forms a purchase needs. based on the SSPR form, the Federal Funds Checklist
# (12/15/25), UC T&Cs, the data security + BAA appendices, IS-3 and FAR 15.403-4

from rules.category_flags import CategoryResult
from rules.funding_rules import FundingDetermination
from rules.models import FormRequirement
from rules.thresholds import ANTI_LOBBYING_THRESHOLD, ThresholdDetermination

SSPR = "SSPR Form"
FEDERAL_FUNDS_CHECKLIST = "Federal Funds Checklist"
ANTI_LOBBYING = "Anti-Lobbying Verification (Byrd Amendment)"
DEBARMENT = "Debarment & Suspension Verification"
UG_FLOWDOWNS = "Uniform Guidance (2 CFR 200) Flow-Down Articles"
FAR_FLOWDOWNS = "FAR Flow-Down Articles"
CERTIFIED_COST_PRICING = "UC Certified Cost or Pricing Data for Federal Contract Purchases"
DATA_SECURITY_APPENDIX = "Appendix Data Security"
BAA = "Business Associate Agreement (BAA)"
IS3 = "IS-3 Compliance"


def route_forms(funding: FundingDetermination, thresholds: ThresholdDetermination,
                categories: CategoryResult) -> list:
    forms = []

    if thresholds.sspr_required:
        forms.append(FormRequirement(
            SSPR, f"${thresholds.evaluated_value:,.0f} meets the ${thresholds.sspr_threshold:,.0f} SSPR threshold",
            f"Sections {', '.join(thresholds.sspr_sections)} "
            f"({thresholds.source_selection.replace('_', ' ')})"))

    if funding.federal_rules_apply:
        forms.append(FormRequirement(FEDERAL_FUNDS_CHECKLIST, "federal requirements apply to this transaction"))
        if thresholds.evaluated_value >= ANTI_LOBBYING_THRESHOLD:
            forms.append(FormRequirement(ANTI_LOBBYING,
                                         f"federal purchase of ${ANTI_LOBBYING_THRESHOLD:,} or more"))
        forms.append(FormRequirement(DEBARMENT, "required for all federally funded orders"))
        if funding.award_type == "contract":
            forms.append(FormRequirement(FAR_FLOWDOWNS, "federal contract funds",
                                         "UC Terms & Conditions Articles 8.1(a) or 8.1(b), 1, 11.10"))
        else:
            forms.append(FormRequirement(UG_FLOWDOWNS, "federal grant/cooperative agreement funds",
                                         "UC Terms & Conditions Articles 1, 8.1(c)(i-v), 11.8, 11.9, 11.10 - "
                                         "these cannot be deleted or edited"))

    if thresholds.certified_cost_pricing_required:
        forms.append(FormRequirement(CERTIFIED_COST_PRICING,
                                     "sole-sourced federal non-commercial contract order of $2,500,000 or more",
                                     "FAR 15.403-4"))

    if categories.needs_data_security_appendix:
        forms.append(FormRequirement(DATA_SECURITY_APPENDIX, "vendor accesses UC institutional data"))
    if categories.needs_baa:
        forms.append(FormRequirement(BAA, "vendor accesses protected health information (HIPAA)"))
    if categories.needs_is3:
        forms.append(FormRequirement(IS3, "vendor provides IT services/software/cloud with UC data"))

    return forms
