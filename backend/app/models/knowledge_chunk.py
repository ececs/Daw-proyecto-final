"""Knowledge Base vector index chunk model mapping.

Manages vectorized partitions of raw external text data (scraped client URLs,
document indices) ensuring compatibility with semantic similarity searching.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

try:
    from pgvector.sqlalchemy import Vector as _Vector
    # Standardized to 768 to optimize semantic search performance.
    _EMBEDDING_TYPE = _Vector(768)
except ImportError:
    from sqlalchemy import LargeBinary
    _EMBEDDING_TYPE = LargeBinary()


class KnowledgeChunk(Base):
    """Represents a single tokenized chunk of source knowledge stored for RAG retrieval.

    Integrates specialized PostgreSQL vector columns with structured JSON metadata
    fields, enabling advanced filtering and semantic lookups by the AI Agent.
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(_EMBEDDING_TYPE, nullable=True)
    # Metadata for filtering (e.g., {"ticket_id": "..."})
    chunk_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
