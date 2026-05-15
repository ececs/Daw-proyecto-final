"""S3 cloud storage file attachment schemas.

Defines metadata payloads for tracking system-wide asset distributions.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel


class AttachmentOut(BaseModel):
    """Serialized output schema reflecting a persistent cloud storage asset.

    Maps localized metadata containing bucket IDs, content keys, size limits,
    and runtime presigned download addresses.
    """
    id: uuid.UUID
    ticket_id: uuid.UUID
    uploader_id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    created_at: datetime
    download_url: str | None = None
    use_for_rag: bool = False

    model_config = {"from_attributes": True}
