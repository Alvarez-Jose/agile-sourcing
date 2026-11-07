"""Explicit server-owned clearance grants; no role/email/department inference."""

from backend.auth.models import UserProfile
from rag_pipeline.documents.models import AccessScope


def policy_scope(user: UserProfile) -> AccessScope:
    if not user.is_approved:
        raise PermissionError("Administrative approval is required")
    # Only exact values stored by an administrator grant additional access.
    grants = {
        "internal": ("public", "internal"),
        "restricted": ("public", "internal", "restricted"),
    }
    return AccessScope(classifications=grants.get(user.clearance, ("public",)))
