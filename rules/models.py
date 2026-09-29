# rules/models.py
# dataclasses shared by the rule engine modules

from dataclasses import dataclass, field
from typing import Optional

FUNDING_TYPES = ("non_federal", "federal_grant", "federal_contract")

SOURCE_SELECTIONS = (
    "competitive_bid",
    "competitive_proposals",
    "sole_source",
    "small_business",
    "professional_services",
    "urgent",
)


@dataclass
class EquipmentItem:
    name: str
    cost: float
    acquired_before_july_2004: bool = False
    is_accessory: bool = False


@dataclass
class PurchaseRequest:
    # amount          = total value of the order/contract (all years, not per year)
    # funding         = "non_federal", "federal_grant" (coop agreements count as grants) or "federal_contract"
    # federal_amount  = federal share. leave it None and it defaults to the full amount for
    #                   federal funding. set it lower than amount for mixed funding
    # contract_years  = length of the agreement. BUS-43 looks at the annual amount for non-federal
    # related_orders  = other orders to the same supplier for the same need (split order check)
    amount: float = 0.0
    funding: str = "non_federal"
    federal_amount: Optional[float] = None
    source_selection: Optional[str] = None
    sole_source_justification: Optional[str] = None
    commercial_item: Optional[bool] = None
    contract_years: float = 1.0
    duration_days: Optional[int] = None
    related_orders: list = field(default_factory=list)
    split_intent: bool = False
    description: str = ""
    items: list = field(default_factory=list)
    vendor_accesses_data: Optional[bool] = None
    vendor_accesses_phi: Optional[bool] = None
    it_services: Optional[bool] = None
    displaces_uc_employees: Optional[bool] = None
    contracting_out_exception: Optional[str] = None

    def __post_init__(self):
        if self.funding not in FUNDING_TYPES:
            raise ValueError(f"funding must be one of {FUNDING_TYPES}, got {self.funding!r}")
        if self.source_selection is not None and self.source_selection not in SOURCE_SELECTIONS:
            raise ValueError(f"source_selection must be one of {SOURCE_SELECTIONS}")
        if self.federal_amount is None:
            self.federal_amount = self.amount if self.funding != "non_federal" else 0.0
        if self.funding == "non_federal" and self.federal_amount:
            raise ValueError("federal_amount given but funding is non_federal; "
                             "use federal_grant or federal_contract with a partial federal_amount")
        if self.federal_amount > self.amount and self.amount:
            raise ValueError("federal_amount cannot exceed amount")
        self.items = [i if isinstance(i, EquipmentItem) else EquipmentItem(*i) for i in self.items]

    @property
    def award_type(self) -> Optional[str]:
        return {"federal_grant": "grant", "federal_contract": "contract"}.get(self.funding)

    @property
    def annual_amount(self) -> float:
        return self.amount / self.contract_years if self.contract_years > 1 else self.amount

    @property
    def term_days(self) -> int:
        return self.duration_days if self.duration_days is not None else int(self.contract_years * 365)


@dataclass
class Flag:
    code: str
    severity: str          # block / require / caution / info
    message: str
    policy: str


@dataclass
class FormRequirement:
    name: str
    reason: str
    detail: str = ""
