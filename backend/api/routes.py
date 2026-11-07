"""
backend/api/routes.py
API routes. The frontend Send button calls POST /api/ask.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints

from backend.rag.pipeline import ask

logger = logging.getLogger("agile_sourcing.api")

router = APIRouter()

# a blank question used to run the classifier, retriever and LLM against arbitrary
# chunks; 2000 chars is ~4x the longest benchmark question, so this only rejects abuse
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(BaseModel):
    question: Question
    think: bool = False


class AskResponse(BaseModel):
    # answer + sources are what the frontend already reads; sources entries keep
    # policy/page and now also carry ref/section/file/text/score/cited
    answer: str
    sources: list[dict]
    citations: list[dict] = []          # the retrieved chunks the answer actually cites ([n])
    rule_sources: list[dict] = []       # provenance for the rule-engine determination
    determination: str | None = None
    intent: str | None = None
    refused: bool = False               # explicit "not found in policy" answer
    refusal_reason: str | None = None
    grounding: dict | None = None       # citation/amount checks, diagnostics only
    llm_called: bool = False            # False for the templated threshold path
    elapsed_ms: int | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    started = time.perf_counter()
    try:
        result = ask(req.question, think=req.think)
    except Exception:
        # the pipeline re-raises Ollama/retrieval failures when the rule engine has no
        # answer; an unlogged 500 hides which stage failed and gives the client nothing
        logger.exception("ask failed")
        raise HTTPException(status_code=503, detail="Policy answer service unavailable")
    return AskResponse(
        answer=result["answer"], sources=result["sources"],
        citations=result.get("citations", []), rule_sources=result.get("rule_sources", []),
        determination=result.get("determination"), intent=result.get("intent"),
        refused=result.get("refused", False), refusal_reason=result.get("refusal_reason"),
        grounding=result.get("grounding"), llm_called=result.get("llm_called", False),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
