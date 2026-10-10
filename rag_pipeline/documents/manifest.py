"""Explicit document identities and review/access metadata, independent of filenames."""

from datetime import datetime
import json
from pathlib import Path
import re

from pydantic import BaseModel, Field, model_validator

from rag_pipeline.documents.models import (
    AccessClass,
    DateObservation,
    ReviewStatus,
    SourceBlock,
)


def normalize_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", Path(value).name.lower())


class ManifestEntry(BaseModel):
    id: str
    filenames: list[str]
    title: str
    policy_id: str | None = None
    category: str = "General Policy"
    kind: str = "other"
    aliases: list[str] = Field(default_factory=list)
    access_classification: AccessClass = "internal"
    review_status: ReviewStatus = "review"
    source_url: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    reviewed_sha256: str | None = None
    review_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_active_review(self):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.id):
            raise ValueError("Document IDs must be stable lowercase slugs")
        if self.review_status == "active" and not (
            self.reviewed_by
            and self.reviewed_at
            and self.reviewed_sha256
            and re.fullmatch(r"[a-f0-9]{64}", self.reviewed_sha256)
        ):
            raise ValueError(
                "Active documents require reviewed_by, reviewed_at, and reviewed_sha256"
            )
        return self


class DocumentManifest:
    def __init__(self, entries: list[ManifestEntry]):
        self.entries = entries
        self.by_filename = {}
        identities = set()
        for entry in entries:
            if entry.id in identities:
                raise ValueError(f"Duplicate manifest ID: {entry.id}")
            identities.add(entry.id)
            for name in entry.filenames:
                normalized = normalize_filename(name)
                previous = self.by_filename.get(normalized)
                if previous and previous.id != entry.id:
                    raise ValueError(f"Ambiguous filename alias: {name}")
                self.by_filename[normalized] = entry

    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text())
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported document manifest schema")
        return cls([ManifestEntry.model_validate(item) for item in data["documents"]])

    def resolve(self, filename: str) -> ManifestEntry:
        try:
            return self.by_filename[normalize_filename(filename)]
        except KeyError:
            raise ValueError(
                f"Register this source in the document manifest: {filename}"
            ) from None


_DATE_LABELS = {
    "effective_date": r"effective\s+date",
    "issued_date": r"issuance\s+date|issued\s+date",
    "review_date": r"last\s+review\s+date",
    "revision_date": r"revised|revision\s+date|rev\.?|updated",
}
_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{1,2}[-/.]\d{4})"


def observe_dates(blocks: list[SourceBlock]) -> list[DateObservation]:
    observations, seen = [], set()
    for block in blocks:
        for line in block.text.splitlines():
            for field, label in _DATE_LABELS.items():
                # Match labelled dates, not arbitrary dates embedded in policy clauses.
                match = re.search(rf"\b(?:{label})\s*[:.\-]?\s*({_DATE})\b", line, re.I)
                if not match:
                    continue
                raw = match.group(1)
                value, precision = None, "day"
                if re.fullmatch(r"\d{1,2}[-/.]\d{4}", raw):
                    month, year = map(int, re.split(r"[-/.]", raw))
                    if 1 <= month <= 12:
                        value, precision = f"{year:04d}-{month:02d}", "month"
                else:
                    for pattern in (
                        "%Y-%m-%d",
                        "%m/%d/%Y",
                        "%m/%d/%y",
                        "%m.%d.%Y",
                        "%m.%d.%y",
                    ):
                        try:
                            value = datetime.strptime(raw, pattern).date().isoformat()
                            break
                        except ValueError:
                            pass
                key = (field, value, block.location.model_dump_json())
                if value and key not in seen:
                    seen.add(key)
                    observations.append(
                        DateObservation(
                            field=field,
                            value=value,
                            precision=precision,
                            text=line,
                            location=block.location,
                        )
                    )
    return observations
