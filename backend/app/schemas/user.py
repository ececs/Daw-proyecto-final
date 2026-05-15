"""User authentication and identification schemas.

Defines response payloads for system profiles exposed through external endpoints.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    """Serialized output schema representing detailed User records.

    Used in API responses to serialize SQLAlchemy models into JSON entities.
    Configured to resolve internal scalar fields from ORM model attributes automatically.
    """
    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
