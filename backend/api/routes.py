"""
backend/api/routes.py
API routes. The frontend Send button calls POST /api/ask.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.dependencies import require_approved_user
from backend.auth.models import UserProfile

router = APIRouter()
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str
    think: bool = False


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(
    req: AskRequest, user: Annotated[UserProfile, Depends(require_approved_user)]
):
    # Login and health endpoints work without loading local ML models or Ollama.
    # Unauthorized requests are rejected before importing or running the pipeline.
    try:
        from backend.rag.pipeline import ask

        result = ask(req.question, think=req.think)
    except ModuleNotFoundError as error:
        logger.exception("Assistant dependency is missing: %s", error.name)
        raise HTTPException(
            503, "The assistant server is not ready yet. Please try again later."
        ) from None
    except HTTPException:
        raise
    except Exception:
        logger.exception("Assistant pipeline failed")
        raise HTTPException(
            503, "The assistant is temporarily unavailable. Please try again later."
        ) from None
    return AskResponse(answer=result["answer"], sources=result["sources"])
