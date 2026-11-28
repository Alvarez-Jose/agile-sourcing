# backend/chat/models.py
# validated chat data; identity and permissions always come from authentication.
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.api.cart_routes import CartRequest, Money

Funding = Literal['unknown', 'federal', 'non_federal', 'federal_grant', 'federal_contract', 'mixed']


class SupplierDetails(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    supplier: str = Field(min_length=1, max_length=200)
    funding: Funding = 'unknown'
    funding_confirmed: StrictBool = True
    tax: Money | None = None
    shipping: Money | None = None
    handling: Money | None = None


class ChatContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cart: CartRequest
    suppliers: list[SupplierDetails] = Field(default_factory=list, max_length=100)
    independent_purchases: StrictBool = False
    pending_question: str | None = Field(default=None, max_length=4000)
    last_question: str | None = Field(default=None, max_length=4000)
    purchase_question: str | None = Field(default=None, max_length=4000)
    sspr_answer_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    awaiting_supplier: str | None = Field(default=None, max_length=200)
    awaiting_kind: str | None = Field(default=None, max_length=40)
    awaiting_field: Literal['tax', 'shipping', 'handling'] | None = None
    captured_at: str = Field(default='', max_length=50)

    @model_validator(mode='after')
    def validate_suppliers(self):
        names = {item.supplier.casefold() for item in self.cart.items}
        supplied = [entry.supplier.casefold() for entry in self.suppliers]
        if len(supplied) != len(set(supplied)) or any(name not in names for name in supplied):
            raise ValueError('Supplier details must match distinct suppliers in the attached cart')
        # Allocations must agree with any displayed cart charge. Unknown charges
        # remain unknown; they are never allocated proportionally or treated as zero.
        if set(supplied) == names:
            for field in ('tax', 'shipping', 'handling'):
                values = [getattr(entry, field) for entry in self.suppliers]
                displayed = getattr(self.cart, field)
                if displayed is not None and all(value is not None for value in values):
                    if abs(sum(values, Decimal('0')) - displayed) > Decimal('0.01'):
                        raise ValueError(f'Supplier {field} allocations do not match the cart')
            # The captured CartRequest validates its own displayed components.
            # Newly supplied estimates for absent components may change a future
            # total; they must not rewrite or be forced to equal that snapshot.
        return self


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)
