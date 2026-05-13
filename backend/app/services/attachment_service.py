"""
Attachment service: file storage (MinIO/R2) + database metadata for ticket attachments.
Returns Pydantic schemas rather than ORM models to keep the API layer decoupled.
"""

import asyncio
import logging
import uuid
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.attachment import Attachment
from app.models.ticket import Ticket
from app.schemas.attachment import AttachmentOut
from app.services import history_service, knowledge_service, storage_service

logger = logging.getLogger(__name__)


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


async def _ingest_attachment_bg(
    attachment_id: str,
    storage_key: str,
    ticket_id: str,
    mime_type: str,
    filename: str,
) -> None:
    """
    Background task: download and index an attachment into RAG knowledge chunks.

    Opens its own session so the HTTP response is not blocked by embedding calls.
    On success, persists a notification for the ticket author + assignee.
    """
    async with AsyncSessionLocal() as db:
        try:
            content = await storage_service.download_file(storage_key)
            result = await knowledge_service.ingest_attachment(
                db,
                attachment_id=attachment_id,
                ticket_id=ticket_id,
                content=content,
                mime_type=mime_type,
            )
            logger.info("RAG ingestion complete: %s", result)
        except Exception as exc:
            logger.warning(
                "Background RAG ingestion failed for attachment %s: %s",
                attachment_id, exc, exc_info=True,
            )
            return

        try:
            ticket_uuid = uuid.UUID(ticket_id)
            ticket = (
                await db.execute(select(Ticket).where(Ticket.id == ticket_uuid))
            ).scalar_one_or_none()
            if ticket:
                from app.services.notification_service import notify_rag_indexed
                await notify_rag_indexed(
                    db,
                    ticket_id=ticket_uuid,
                    author_id=ticket.author_id,
                    assignee_id=ticket.assignee_id,
                    message=f'Attachment indexed for RAG: {filename}',
                )
        except Exception as exc:
            logger.warning("Could not send RAG-indexed notification: %s", exc)


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
    """Upload a file to storage, save metadata, and record history."""
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    if not ticket_result.scalar_one_or_none():
        return None

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

    await history_service.record_change(
        db,
        ticket_id=ticket_id,
        actor_id=uploader_id,
        field="attachment_added",
        old_value=None,
        new_value=filename,
    )
    await db.commit()

    return await _to_schema(attachment)


async def delete_attachment(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> bool:
    """Delete an attachment from storage and database, and record history."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()

    if not attachment or attachment.uploader_id != actor_id:
        return False

    ticket_id = attachment.ticket_id
    filename = attachment.filename
    storage_key = attachment.storage_key

    await history_service.record_change(
        db,
        ticket_id=ticket_id,
        actor_id=actor_id,
        field="attachment_removed",
        old_value=filename,
        new_value=None,
    )
    # Delete DB metadata first. If storage cleanup fails afterwards, the user
    # still gets a consistent application state and the leftover object can be
    # cleaned up later.
    await db.delete(attachment)
    await db.commit()

    await knowledge_service.delete_attachment_chunks(db, str(attachment_id))

    try:
        await storage_service.delete_file(storage_key)
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

    Persists the flag immediately and returns. Ingestion runs as a background
    task so the HTTP response is not blocked by embedding API calls.
    """
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    if not attachment:
        return None

    attachment.use_for_rag = use_for_rag
    await db.commit()
    await db.refresh(attachment)

    if use_for_rag:
        # Fire-and-forget: avoids blocking the HTTP response on ~15 embedding calls
        asyncio.create_task(_ingest_attachment_bg(
            attachment_id=str(attachment.id),
            storage_key=attachment.storage_key,
            ticket_id=str(attachment.ticket_id),
            mime_type=attachment.mime_type,
            filename=attachment.filename,
        ))
    else:
        await knowledge_service.delete_attachment_chunks(db, str(attachment_id))

    return await _to_schema(attachment)
