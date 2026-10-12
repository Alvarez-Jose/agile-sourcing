"""
backend/api/routes.py
API routes. The frontend Send button calls POST /api/ask.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.rag.pipeline import ask

router = APIRouter()


class AskRequest(BaseModel):
    question: str
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


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    result = ask(req.question, think=req.think)
    return AskResponse(
        answer=result["answer"], sources=result["sources"],
        citations=result.get("citations", []), rule_sources=result.get("rule_sources", []),
        determination=result.get("determination"), intent=result.get("intent"),
        refused=result.get("refused", False), refusal_reason=result.get("refusal_reason"),
    )
