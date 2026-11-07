"""Typed, evidence-backed policy graph. References are not inferred overrides."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from rag_pipeline.documents.models import AccessClass, Evidence, ReviewStatus


class PolicyNode(BaseModel):
    id: str
    kind: Literal["document", "section", "form", "reference"]
    label: str
    document_version_id: str | None = None
    access_classification: AccessClass = "internal"
    review_status: ReviewStatus = "review"
    properties: dict = Field(default_factory=dict)


class PolicyEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: Literal["contains", "has_source", "references", "overrides"]
    evidence: list[Evidence]
    conditions: dict | None = None
    verified_by: str | None = None
    verified_at: str | None = None

    @model_validator(mode="after")
    def require_evidence_and_override_review(self):
        if not self.evidence or any(not item.quote.strip() for item in self.evidence):
            raise ValueError("Every relationship requires supporting source evidence")
        if self.relation == "overrides" and not (
            self.conditions
            and self.verified_by
            and self.verified_by.strip()
            and self.verified_at
        ):
            raise ValueError(
                "Overrides require explicit conditions and a recorded reviewer/date"
            )
        if self.relation == "overrides":
            datetime.fromisoformat(self.verified_at.replace("Z", "+00:00"))
        return self
