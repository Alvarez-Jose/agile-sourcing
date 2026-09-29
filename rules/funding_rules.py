# rules/funding_rules.py
# figures out if federal rules apply, including mixed funding.
#
# mixed funding rule is from the SSPR FAQ (V 4.2021): $100K total with $9K federal and
# $91K state -> state law only. if the federal part is over $10K then federal rules
# apply to the WHOLE transaction, not just the federal part.

from dataclasses import dataclass
from typing import Optional

from rules.models import PurchaseRequest

MIXED_FUNDING_FEDERAL_TRIGGER = 10_000   # has to be OVER this, exactly $10K is still state rules


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

    if fed > MIXED_FUNDING_FEDERAL_TRIGGER:
        return FundingDetermination(
            req.amount, fed, non_fed, award, True, True,
            f"Mixed funding: ${fed:,.0f} federal + ${non_fed:,.0f} non-federal. Because the federal "
            f"portion exceeds ${MIXED_FUNDING_FEDERAL_TRIGGER:,}, federal requirements apply to the "
            f"ENTIRE ${req.amount:,.0f} transaction, not just the federal portion (SSPR FAQ).",
        )

    return FundingDetermination(
        req.amount, fed, non_fed, award, True, False,
        f"Mixed funding: ${fed:,.0f} federal + ${non_fed:,.0f} non-federal. Because the federal "
        f"portion does not exceed ${MIXED_FUNDING_FEDERAL_TRIGGER:,}, only UC/State rules apply to "
        "the transaction (SSPR FAQ).",
    )
