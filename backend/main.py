"""
backend/main.py
FastAPI app entry point.

Run locally:
    uvicorn backend.main:app --reload --port 8000

The frontend Send button should POST to:
    http://localhost:8000/api/ask
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.auth_routes import router as auth_router

@asynccontextmanager
async def lifespan(app):
    # Auth/health remain available without local models or a policy database.
    if os.getenv("RAG_WARM_UP") == "1":
        from starlette.concurrency import run_in_threadpool
        try:
            from backend.rag.pipeline import warm_up
            await run_in_threadpool(warm_up)
        except Exception:
            logging.getLogger(__name__).exception("Optional RAG warm-up failed")
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
