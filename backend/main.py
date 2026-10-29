"""
backend/main.py
FastAPI app entry point.

Run locally:
    uvicorn backend.main:app --reload --port 8000

The frontend Send button should POST to:
    http://localhost:8000/api/ask
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.auth_routes import router as auth_router
from backend.rag.pipeline import warm_up


@asynccontextmanager
async def lifespan(app):
    # load the retriever, reranker and LLM once at startup instead of on the first question
    warm_up()
    yield


app = FastAPI(title="Agile Sourcing API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to the extension origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(auth_router)
