"""Reusable dependencies: token identity, fresh Firestore profile, and approval."""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
from google.auth.exceptions import GoogleAuthError
from pydantic import ValidationError

from backend.auth.firebase import get_firebase_app, get_firestore_client
from backend.auth.models import UserProfile

logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="A valid Firebase ID token is required. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict:
    if credentials is None:
        raise unauthorized()
    app = get_firebase_app()
    try:
        identity = auth.verify_id_token(
            credentials.credentials, app=app, check_revoked=True
        )
    except (
        auth.InvalidIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ):
        raise unauthorized() from None
    except (auth.CertificateFetchError, exceptions.FirebaseError, GoogleAuthError):
        logger.exception("Firebase token verification unavailable")
        raise HTTPException(
            503, "Authentication service unavailable. Please retry."
        ) from None
    if not identity.get("uid") or not identity.get("email"):
        raise unauthorized()
    return identity


def get_current_user(
    identity: Annotated[dict, Depends(verify_identity)]
) -> UserProfile:
    """Only the verified UID selects the document; client permissions are never used."""
    db = get_firestore_client()
    defaults = {
        "uid": identity["uid"],
        "email": identity["email"],
        "name": identity.get("name"),
        "photoURL": identity.get("picture"),
        "department": None,
        "clearance": "none",
        "is_approved": False,
        "role": "buyer",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        document = db.collection("users").document(identity["uid"])
        snapshot = document.get(retry=None, timeout=10)
        if not snapshot.exists:
            try:
                # create() avoids overwriting permissions if two first logins race.
                document.create(defaults, retry=None, timeout=10)
                data = defaults
            except AlreadyExists:
                data = document.get(retry=None, timeout=10).to_dict()
        else:
            data = snapshot.to_dict()
        profile = {
            **defaults,
            **(data or {}),
            "uid": identity["uid"],
            "email": identity["email"],
        }
        return UserProfile.model_validate(profile)
    except (GoogleAPICallError, GoogleAuthError, ValidationError):
        logger.exception("User profile could not be loaded")
        raise HTTPException(503, "User profile unavailable. Please retry.") from None


def require_approved_user(
    user: Annotated[UserProfile, Depends(get_current_user)]
) -> UserProfile:
    if not user.is_approved:
        raise HTTPException(403, "Your account is pending administrative approval.")
    return user
