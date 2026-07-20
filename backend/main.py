"""
backend/main.py
FastAPI app entry point.

Run locally:
    uvicorn backend.main:app --reload --port 8000

The frontend Send button should POST to:
    http://localhost:8000/api/ask
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(title="Agile Sourcing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to the extension origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
