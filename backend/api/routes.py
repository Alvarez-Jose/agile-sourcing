"""
backend/api/routes.py
API routes. The frontend Send button calls POST /api/ask.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.auth.dependencies import require_approved_user
from backend.auth.models import UserProfile
from backend.auth.policy_access import policy_scope

router = APIRouter()
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    think: bool = False

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank")
        return value


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    citations: list[dict] = Field(default_factory=list)
    rule_sources: list[dict] = Field(default_factory=list)
    determination: str | None = None
    intent: str | None = None
    refused: bool = False
    refusal_reason: str | None = None
    llm_called: bool = False


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

        result = ask(req.question, think=req.think, scope=policy_scope(user))
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
    return AskResponse.model_validate(result)
