"""
Attachment service: file storage (MinIO/R2) + database metadata for ticket attachments.
Returns Pydantic schemas rather than ORM models to keep the API layer decoupled.
"""

import logging
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

from app.models.attachment import Attachment
from app.models.ticket import Ticket
from app.schemas.attachment import AttachmentOut
from app.services import knowledge_service, storage_service


async def _to_schema(attachment: Attachment) -> AttachmentOut:
    """Build AttachmentOut from an ORM instance, fetching a fresh presigned URL."""
    try:
        url = await storage_service.get_presigned_url(attachment.storage_key)
    except Exception:
        # Presigned URL generation is best-effort; a missing URL is preferable to
        # surfacing a storage error on every attachment list.
        url = None
    return AttachmentOut(
        id=attachment.id,
        ticket_id=attachment.ticket_id,
        uploader_id=attachment.uploader_id,
        filename=attachment.filename,
        size_bytes=attachment.size_bytes,
        mime_type=attachment.mime_type,
        created_at=attachment.created_at,
        download_url=url,
        use_for_rag=attachment.use_for_rag,
    )


async def list_attachments(
    db: AsyncSession,
    ticket_id: uuid.UUID,
) -> List[AttachmentOut]:
    """Return all attachments for a ticket ordered by upload time."""
    result = await db.execute(
        select(Attachment)
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.asc())
    )
    return [await _to_schema(att) for att in result.scalars().all()]


async def create_attachment(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    uploader_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: str,
) -> Optional[AttachmentOut]:
    """
    Uploads a file to storage and saves metadata to the database.
    """
    # 1. Verify ticket
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    if not ticket_result.scalar_one_or_none():
        return None

    # 2. Upload to storage (MinIO/R2)
    storage_key = await storage_service.upload_file(
        ticket_id=ticket_id,
        filename=filename,
        content=content,
        mime_type=mime_type,
    )

    # 3. Save metadata — if the DB commit fails, clean up the orphaned file
    attachment = Attachment(
        ticket_id=ticket_id,
        uploader_id=uploader_id,
        filename=filename,
        storage_key=storage_key,
        size_bytes=len(content),
        mime_type=mime_type,
    )
    db.add(attachment)
    try:
        await db.commit()
        await db.refresh(attachment)
    except Exception:
        try:
            await storage_service.delete_file(storage_key)
        except Exception:
            pass
        raise

    return await _to_schema(attachment)


async def delete_attachment(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> bool:
    """
    Deletes an attachment from both storage and database.
    """
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    
    if not attachment or attachment.uploader_id != actor_id:
        return False

    # Delete DB metadata first. If storage cleanup fails afterwards, the user
    # still gets a consistent application state and the leftover object can be
    # cleaned up later.
    await db.delete(attachment)
    await db.commit()

    # Clean up any knowledge chunks indexed from this attachment
    await knowledge_service.delete_attachment_chunks(db, str(attachment_id))

    try:
        await storage_service.delete_file(attachment.storage_key)
    except Exception:
        pass
    return True


async def update_attachment_rag(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    use_for_rag: bool,
) -> Optional[AttachmentOut]:
    """
    Toggle RAG indexing for an attachment.

    When enabled: downloads the file from storage, extracts text, chunks,
    embeds, and persists to knowledge_chunks.
    When disabled: removes all associated knowledge chunks.
    """
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    if not attachment:
        return None

    attachment.use_for_rag = use_for_rag
    await db.commit()
    await db.refresh(attachment)

    if use_for_rag:
        try:
            logger.info("RAG ingestion starting for attachment %s", attachment.id)
            content = await storage_service.download_file(attachment.storage_key)
            logger.info("RAG download OK (%d bytes), extracting text...", len(content))
            result = await knowledge_service.ingest_attachment(
                db,
                attachment_id=str(attachment.id),
                ticket_id=str(attachment.ticket_id),
                content=content,
                mime_type=attachment.mime_type,
            )
            logger.info("RAG ingestion complete: %s", result)
        except Exception as exc:
            # Ingestion failure is non-fatal: the flag is already set and the user
            # can retry by toggling the checkbox again.
            logger.warning("RAG ingestion failed for attachment %s: %s", attachment.id, exc, exc_info=True)
    else:
        await knowledge_service.delete_attachment_chunks(db, str(attachment_id))

    return await _to_schema(attachment)

