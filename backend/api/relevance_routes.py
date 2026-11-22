"""
backend/api/relevance_routes.py
POST /api/relevance — check which search results match the user's intent.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.dependencies import require_approved_user
from backend.auth.models import UserProfile
from backend.rag.relevance import ItemFlag

logger = logging.getLogger(__name__)
router = APIRouter()


class RelevanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str = Field(min_length=1, max_length=500)
    items: list[str] = Field(min_length=1, max_length=100)


class RelevanceResponse(BaseModel):
    flags: list[ItemFlag]
    relevant_count: int
    irrelevant_count: int
    elapsed_ms: int


@router.post("/relevance", response_model=RelevanceResponse)
def relevance_endpoint(
    req: RelevanceRequest,
    user: Annotated[UserProfile, Depends(require_approved_user)],
):
    started = time.perf_counter()
    try:
        from backend.rag.relevance import check_relevance

        result = check_relevance(req.search, req.items)
    except Exception:
        logger.exception("Relevance check failed")
        raise HTTPException(503, "Relevance service temporarily unavailable.") from None

    relevant_count = sum(1 for f in result.flags if f.relevant)
    irrelevant_count = len(result.flags) - relevant_count
    elapsed = int((time.perf_counter() - started) * 1000)

    # Console output (server-side)
    print(f"\n{'='*60}")
    print(f"Relevance check: \"{req.search}\" ({len(result.flags)} items, {elapsed}ms)")
    print(f"{'='*60}")
    for f in result.flags:
        status = "MATCH " if f.relevant else "FLAG  "
        print(f"  [{status}] {f.item}  ({f.reason})")
    print(f"  {relevant_count} relevant, {irrelevant_count} flagged\n")

    return RelevanceResponse(
        flags=result.flags,
        relevant_count=relevant_count,
        irrelevant_count=irrelevant_count,
        elapsed_ms=elapsed,
    )