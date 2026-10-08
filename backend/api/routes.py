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
    answer: str
    sources: list[dict]


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    result = ask(req.question, think=req.think)
    return AskResponse(answer=result["answer"], sources=result["sources"])
