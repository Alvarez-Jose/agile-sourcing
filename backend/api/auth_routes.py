from typing import Annotated

from fastapi import APIRouter, Depends, Response

from backend.auth.dependencies import get_current_user
from backend.auth.models import UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=UserProfile)
def establish_session(
    response: Response,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> UserProfile:
    response.headers["Cache-Control"] = "no-store"
    return user


@router.get("/me", response_model=UserProfile)
def current_profile(
    response: Response,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> UserProfile:
    response.headers["Cache-Control"] = "no-store"
    return user
