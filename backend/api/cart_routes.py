"""Authenticated, two-source SSPR demo; independent of the general RAG pipeline."""

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.auth.dependencies import require_approved_user
from backend.auth.models import UserProfile
from rules import thresholds as T
from rules.provenance import DOCUMENTS, SOURCES

router = APIRouter(prefix="/api/cart", tags=["cart demo"])
ROOT = Path(__file__).resolve().parents[2]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class CartItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=500)
    supplier: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    unit_price: Money
    line_total: Money

    @model_validator(mode="after")
    def reconcile(self):
        if abs(self.quantity * self.unit_price - self.line_total) > Decimal("0.01"):
            raise ValueError("Item quantity times unit price does not match the line total")
        return self


class CartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CartItem] = Field(min_length=1, max_length=100)
    currency: Literal["USD"]
    subtotal: Money
    tax: Money | None = None
    shipping: Money | None = None
    handling: Money | None = None
    total: Money | None = None
    funding: Literal["unknown", "non_federal", "federal_contract", "federal_grant", "mixed"] = "unknown"
    reviewed: StrictBool = False
    single_purchase: StrictBool = False

    @model_validator(mode="after")
    def reconcile(self):
        if abs(sum(i.line_total for i in self.items) - self.subtotal) > Decimal("0.01"):
            raise ValueError("Cart subtotal does not match its item lines; read the whole cart again")
        charges = (self.tax, self.shipping, self.handling)
        if self.total is not None and all(x is not None for x in charges):
            if abs(self.subtotal + sum(charges) - self.total) > Decimal("0.01"):
                raise ValueError("Cart charges do not reconcile with the displayed total")
        return self


def reviewed_sources():
    """Read only the two pinned, reviewed PDFs, without opening the Chroma corpus."""
    from pypdf import PdfReader

    manifest = json.loads((ROOT / "data/policies/document_manifest.json").read_text())
    sources = []
    specs = [("sspr-form", "SSPR_Official_UCSC_2025-12.pdf", 1),
             ("bus-43", "BUS-43_Interim_2026-01-26.pdf", 9)]
    for doc_id, filename, page in specs:
        entry = next(d for d in manifest["documents"] if d["id"] == doc_id)
        path = ROOT / "data/raw_policies" / filename
        if (entry["review_status"] != "active" or entry["access_classification"] != "public"
                or not path.is_file() or sha256(path.read_bytes()).hexdigest() != entry["reviewed_sha256"]):
            raise ValueError("Reviewed demo source missing or changed")
        text = " ".join((PdfReader(path).pages[page - 1].extract_text() or "").split())
        if doc_id == "sspr-form":
            start = text.index("This document must be completed")
            quote = text[start:text.index("Locations are strongly encouraged", start)].strip()
        else:
            quote = SOURCES["COMPETITIVE_BID_THRESHOLD"][0].quote
            if quote not in text:
                raise ValueError("Reviewed policy quote changed")
        sources.append({"citation_id": len(sources) + 1, "policy": DOCUMENTS[doc_id]["title"],
                        "page": str(page), "section": "Form applicability" if doc_id == "sspr-form" else "III.C.1",
                        "source_url": DOCUMENTS[doc_id]["url"], "evidence": [{"quote": quote}]})
    return sources


def guide(cart: CartRequest, sources: list[dict]):
    questions = []
    if not cart.reviewed:
        questions.append("Confirm that all item lines and amounts match your current cart.")
    if not cart.single_purchase:
        questions.append("Confirm this is one standalone goods purchase, not services, a multi-year agreement, or part of related orders.")
    if len({i.supplier.casefold() for i in cart.items}) != 1:
        questions.append("This demo covers one supplier at a time; ask Procurement about the separate transactions in this cart.")
    if cart.funding == "unknown":
        questions.append("Will this use non-federal funds, a federal contract, or a federal grant/cooperative agreement?")
    if cart.funding == "mixed":
        questions.append("Mixed funding needs a separate review of the federal portion; it is outside this demo.")
    for name in ("shipping", "handling"):
        if getattr(cart, name) is None:
            questions.append(f"Enter the estimated {name} amount, or explicitly confirm it is zero. The cart does not establish it.")
    if cart.funding in ("federal_contract", "federal_grant") and cart.tax is None:
        questions.append("Enter estimated tax; the SSPR form includes it for federally funded purchases.")
    common = {"scope": "SSPR applicability only; not a complete list of required paperwork or purchase approval.",
              "sources": sources, "questions": questions, "forms": [], "llm_called": False}
    if questions:
        return {**common, "status": "needs_details", "answer": "Before checking the SSPR form, please confirm:\n" +
                "\n".join(f"• {q}" for q in questions)}
    threshold = {"non_federal": T.SSPR_NON_FEDERAL, "federal_contract": T.SSPR_FEDERAL_CONTRACT,
                 "federal_grant": T.SSPR_FEDERAL_GRANT}[cart.funding]
    amount = cart.subtotal + cart.shipping + cart.handling
    basis = "subtotal plus estimated shipping/handling, excluding tax"
    if cart.funding != "non_federal":
        amount += cart.tax
        basis = "subtotal plus estimated tax, shipping, and handling"
    required = amount >= threshold
    answer = (f"Based on the confirmed estimates, the assessed amount is ${amount:,.2f} ({basis}). "
              f"The reviewed SSPR form lists a ${threshold:,.2f} threshold for this funding type [1].\n\n")
    if required:
        common["forms"] = [{"name": "Source Selection & Price Reasonableness Justification Form (SSPR)",
                            "url": DOCUMENTS["sspr-form"]["url"]}]
        answer += ("This purchase meets that SSPR threshold. Prepare the form and select the appropriate source-selection "
                   "basis in Section I; the remaining sections depend on that choice. A PunchOut tile or contract link "
                   "alone does not establish which box to select.\n\n")
    else:
        answer += "This purchase is below the form's stated SSPR threshold. That does not establish that no other paperwork is needed.\n\n"
    answer += ("BUS-43 describes competitive-bidding requirements with exceptions [2]. This limited check does not "
               "resolve contract coverage, exceptions, annual aggregation, or campus/item-specific requirements. "
               "Confirm those with Procurement before submission.")
    return {**common, "status": "checked", "answer": answer, "sspr_required_by_threshold": required,
            "assessed_amount": f"{amount:.2f}", "threshold": f"{threshold:.2f}"}


@router.post("/guide")
def cart_guide(cart: CartRequest, user: Annotated[UserProfile, Depends(require_approved_user)]):
    try:
        sources = reviewed_sources()
    except (OSError, ValueError, KeyError, StopIteration, IndexError):
        raise HTTPException(503, "The reviewed BUS-43/SSPR demo sources are missing or changed; restore the reviewed copies.") from None
    return guide(cart, sources)
