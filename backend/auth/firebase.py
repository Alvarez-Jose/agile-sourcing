"""Initialize Admin SDK lazily, using server-side Application Default Credentials."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

import firebase_admin
from dotenv import load_dotenv
from fastapi import HTTPException
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)
APP_NAME = "agile-sourcing-api"
_initialization_lock = Lock()
SECRET_DIR = Path(__file__).resolve().parents[2] / "secret"
load_dotenv(SECRET_DIR / ".env")

# Relative credential paths in secret/.env are relative to that directory,
# independent of the directory used to start FastAPI.
credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if credential_path:
    credential_file = Path(credential_path).expanduser()
    if not credential_file.is_absolute():
        credential_file = SECRET_DIR / credential_file
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credential_file.resolve())


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    with _initialization_lock:
        try:
            return firebase_admin.get_app(APP_NAME)
        except ValueError:
            pass

        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv(
            "VITE_FIREBASE_PROJECT_ID"
        )
        if not project_id:
            raise HTTPException(
                503, "Set FIREBASE_PROJECT_ID in secret/.env or the server environment."
            )
        try:
            return firebase_admin.initialize_app(
                credentials.ApplicationDefault(),
                {"projectId": project_id},
                name=APP_NAME,
            )
        except Exception:
            logger.exception("Firebase Admin initialization failed")
            raise HTTPException(
                503, "Firebase Admin credentials are not configured."
            ) from None


@lru_cache(maxsize=1)
def get_firestore_client():
    app = get_firebase_app()
    try:
        return firestore.client(app=app)
    except Exception:
        logger.exception("Firestore client initialization failed")
        raise HTTPException(503, "Firestore credentials are not configured.") from None
