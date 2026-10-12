# rules/funding_rules.py
# figures out if federal rules apply, including mixed funding.
#
# mixed funding rule is from the SSPR form (Rev. 12-2025, p.1 Section I): "For mixed
# funding where the federal portion exceeds the above thresholds, check Federal side
# only." the "above thresholds" are the form's federal ones: >= $15,000 for federal
# contracts and >= $50,000 for grants/cooperative agreements. when the federal portion
# reaches its threshold, federal rules apply to the WHOLE transaction.
#
# the form says "exceeds" but states the thresholds themselves as ">=", so a federal
# portion of exactly $15,000 / $50,000 counts as meeting them (same boundary as SSPR).
#
# this replaces the old flat "> $10,000" trigger from the SSPR FAQ (V 4.2021), which
# was the pre-Oct 2025 federal micro-purchase threshold.

from dataclasses import dataclass
from typing import Optional

from rules.models import PurchaseRequest

MIXED_FUNDING_FEDERAL_TRIGGERS = {
    "contract": 15_000,   # SSPR form: Federal Contract purchases >= $15,000
    "grant": 50_000,      # SSPR form: Federal Grant/Cooperative Agreement purchases >= $50,000
}


def mixed_funding_trigger(award_type: Optional[str]) -> int:
    return MIXED_FUNDING_FEDERAL_TRIGGERS.get(award_type, MIXED_FUNDING_FEDERAL_TRIGGERS["grant"])


@dataclass
class FundingDetermination:
    total: float
    federal_amount: float
    non_federal_amount: float
    award_type: Optional[str]       # "grant" | "contract" | None
    is_mixed: bool
    federal_rules_apply: bool
    explanation: str

    @property
    def regime(self) -> str:
        if not self.federal_rules_apply:
            return "non_federal"
        return f"federal_{self.award_type}"


def determine_funding(req: PurchaseRequest) -> FundingDetermination:
    fed = req.federal_amount or 0.0
    non_fed = max(req.amount - fed, 0.0)
    is_mixed = fed > 0 and non_fed > 0
    award = req.award_type
    award_label = {"grant": "federal grant/cooperative agreement", "contract": "federal contract"}.get(award, "")

    if fed == 0:
        return FundingDetermination(
            req.amount, 0.0, non_fed, None, False, False,
            f"This ${req.amount:,.0f} purchase uses no federal funds, so UC/State rules "
            "(BUS-43, CA Public Contract Code) apply.",
        )

    if not is_mixed:
        return FundingDetermination(
            req.amount, fed, 0.0, award, False, True,
            f"This ${req.amount:,.0f} purchase is fully funded by a {award_label}, so federal "
            f"requirements ({'2 CFR 200 Uniform Guidance' if award == 'grant' else 'FAR'}) apply "
            "in addition to UC policy.",
        )

    trigger = mixed_funding_trigger(award)
    if fed >= trigger:
        return FundingDetermination(
            req.amount, fed, non_fed, award, True, True,
            f"Mixed funding: ${fed:,.0f} federal + ${non_fed:,.0f} non-federal. Because the federal "
            f"portion meets the ${trigger:,} {award_label} threshold, federal requirements apply to the "
            f"ENTIRE ${req.amount:,.0f} transaction, not just the federal portion (SSPR form Rev. 12-2025, "
            "Section I: check Federal side only).",
        )

    return FundingDetermination(
        req.amount, fed, non_fed, award, True, False,
        f"Mixed funding: ${fed:,.0f} federal + ${non_fed:,.0f} non-federal. Because the federal "
        f"portion is below the ${trigger:,} {award_label} threshold, only UC/State rules apply to "
        "the transaction (SSPR form Rev. 12-2025, Section I).",
    )
