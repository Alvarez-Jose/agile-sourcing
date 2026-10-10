"""Records for the source index. Locations never fabricate DOCX page numbers."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

AccessClass = Literal["public", "internal", "restricted"]
ReviewStatus = Literal["review", "active", "archived"]


class SourceLocation(BaseModel):
    file: str
    format: Literal["pdf", "docx"]
    page: int | None = None
    part: str | None = None
    element: str | None = None
    bbox: list[float] | None = None

    @model_validator(mode="after")
    def validate_page(self):
        if self.page is not None and (self.format == "docx" or self.page < 1):
            raise ValueError("Only PDFs have known, one-based physical page numbers")
        return self


class TableCell(BaseModel):
    text: str
    column_span: int = 1
    vertical_merge: str | None = None


class SourceLink(BaseModel):
    text: str
    target: str
    location: SourceLocation
    raw_target_base64: str | None = None
    encoding: str | None = None


class SourceBlock(BaseModel):
    id: str
    kind: Literal["text", "heading", "table", "header", "footer", "textbox", "footnote"]
    text: str
    location: SourceLocation
    heading_level: int | None = None
    heading_hints: list[dict] = Field(default_factory=list)
    links: list[SourceLink] = Field(default_factory=list)
    # Physical XML/PDF cells, including merge metadata; no overwritten source cells.
    rows: list[list[TableCell]] = Field(default_factory=list)


class DateObservation(BaseModel):
    field: Literal["effective_date", "revision_date", "issued_date", "review_date"]
    value: str
    precision: Literal["day", "month", "year"]
    text: str
    location: SourceLocation


class DocumentRecord(BaseModel):
    id: str
    version_id: str
    sha256: str
    file: str
    title: str
    policy_id: str | None = None
    category: str = "General Policy"
    kind: str = "other"
    access_classification: AccessClass = "internal"
    review_status: ReviewStatus = "review"
    source_url: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    additional_files: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    dates: list[DateObservation] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    blocks: list[SourceBlock] = Field(default_factory=list)


class SectionBlock(BaseModel):
    block_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    source_start: int = Field(default=0, ge=0)
    source_end: int | None = None
    location: SourceLocation
    kind: str


class SectionRecord(BaseModel):
    id: str
    document_version_id: str
    ordinal: int
    title: str
    parent_section_id: str | None = None
    kind: str = "body"
    text: str
    blocks: list[SectionBlock] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    id: str
    document_version_id: str
    parent_section_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str
    token_count: int = Field(gt=0)
    tokenizer: str = "lexical-v1"
    locations: list[SourceLocation] = Field(default_factory=list)


class Evidence(BaseModel):
    document_version_id: str
    section_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str
    locations: list[SourceLocation]
    link_target: str | None = None


class AccessScope(BaseModel):
    """Trusted caller scope, not values supplied in a user query or an LLM prompt.

    Default reads expose only active public documents. CLI review tools explicitly
    opt into local internal/restricted and unreviewed records.
    """

    classifications: tuple[AccessClass, ...] = ("public",)
    include_review: bool = False
    include_archived: bool = False

    def permits(self, classification: str, status: str) -> bool:
        return classification in self.classifications and (
            status == "active"
            or (status == "review" and self.include_review)
            or (status == "archived" and self.include_archived)
        )


LOCAL_REVIEW_SCOPE = AccessScope(
    classifications=("public", "internal", "restricted"),
    include_review=True,
    include_archived=True,
)
