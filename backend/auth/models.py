from datetime import datetime

from pydantic import BaseModel, StrictBool


class UserProfile(BaseModel):
    uid: str
    email: str
    name: str | None = None
    photoURL: str | None = None
    department: str | None = None
    clearance: str = "none"
    is_approved: StrictBool = False
    role: str = "buyer"
    created_at: datetime | None = None
