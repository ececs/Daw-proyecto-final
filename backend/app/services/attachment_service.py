"""Attachment service.

Owns metadata for ticket attachments. Delegates blob handling to
`storage_service` and RAG indexing to `knowledge_service`. Files marked
with `use_for_rag=True` are indexed in a background task so the HTTP
response is not blocked by the embedding pipeline.
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
    """Convert an `Attachment` ORM row into its response schema.

    The `download_url` is generated on the fly as a presigned URL; a
    storage failure is degraded to `None` so the rest of the metadata is
    still served.
    """
    try:
        url = await storage_service.get_presigned_url(attachment.storage_key)
    except Exception:
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
    """Download the file and index it as RAG knowledge in a background task.

    Runs in its own SQLAlchemy session so a failure here cannot taint the
    caller's transaction. On successful ingestion, a `rag_indexed`
    notification is sent to the ticket's author and assignee.
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
    """Return every attachment of a ticket with a freshly generated download URL.

    Returns:
        list[AttachmentOut]: Attachments ordered from oldest to newest.
    """
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
    """Upload the file to storage and persist its metadata atomically.

    If the database commit fails after the upload, the orphan blob in
    storage is deleted in a best-effort compensation step so we do not
    leak files. A history entry (`attachment_added`) is recorded after
    the successful commit.

    Returns:
        AttachmentOut | None: The persisted attachment, or `None` if the
        parent ticket does not exist.
    """
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    if not ticket_result.scalar_one_or_none():
        return None

    storage_key = await storage_service.upload_file(
        ticket_id=ticket_id,
        filename=filename,
        content=content,
        mime_type=mime_type,
    )

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
        # Why: compensate the side-effecting upload so a failed commit
        # does not leave an orphan blob in object storage.
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
    """Delete an attachment, its RAG chunks and the underlying blob.

    Only the uploader is authorised. The storage deletion is best-effort:
    if the bucket call fails, the metadata is still removed (the file
    will be a lonely orphan but the row will be gone).

    Returns:
        bool: `True` on success; `False` if the attachment is missing or
        the actor is not the uploader.
    """
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
    """Toggle the RAG-indexing flag for an attachment.

    Enabling the flag schedules a background ingestion task; disabling it
    removes any chunks already indexed for the attachment.

    Returns:
        AttachmentOut | None: The updated attachment, or `None` if it
        does not exist.
    """
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    if not attachment:
        return None

    attachment.use_for_rag = use_for_rag
    await db.commit()
    await db.refresh(attachment)

    if use_for_rag:
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
