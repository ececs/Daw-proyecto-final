"""Ticket attachments endpoints.

Routes nested under `/tickets/{ticket_ref}/attachments` for uploading,
listing, deleting and toggling the RAG-indexing flag of files attached to
a ticket. Enforces size and MIME-type limits configured in
`app.core.config.settings`.
"""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, status
from app.core.config import settings
from app.core.dependencies import CurrentUser, DB
from app.schemas.attachment import AttachmentOut
from app.services import attachment_service, notification_service, ticket_service
from app.schemas.websocket import WSMessageType

router = APIRouter(prefix="/tickets", tags=["Attachments"])

MAX_BYTES = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


@router.get(
    "/{ticket_ref}/attachments",
    response_model=List[AttachmentOut],
    summary="List attachments for a ticket",
)
async def list_attachments(ticket_ref: str, db: DB, current_user: CurrentUser):
    """Return every attachment of the ticket.

    Returns:
        list[AttachmentOut]: Attachment metadata (file content is fetched
        separately via the storage URL).

    Raises:
        HTTPException: **404** if the ticket does not exist.
    """
    ticket = await ticket_service.resolve_ticket(db, ticket_ref)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return await attachment_service.list_attachments(db, ticket.id)


@router.post(
    "/{ticket_ref}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file attachment",
)
async def upload_attachment(
    ticket_ref: str,
    file: UploadFile,
    db: DB,
    current_user: CurrentUser,
):
    """Upload a file and attach it to the ticket.

    Validates the binary against the configured size limit
    (`MAX_ATTACHMENT_SIZE_MB`) and MIME-type allow-list **before** any
    persistence happens, so rejected uploads never touch storage. On
    success, broadcasts a `TICKET_UPDATED` WebSocket event so connected
    clients refresh the attachment list.

    Returns:
        AttachmentOut: Metadata of the persisted attachment.

    Raises:
        HTTPException: **413** if the file exceeds the size limit.
        HTTPException: **415** if the MIME type is not allowed.
        HTTPException: **404** if the ticket does not exist.
    """
    content = await file.read()

    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_ATTACHMENT_SIZE_MB}MB limit",
        )

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime_type}' is not allowed",
        )

    ticket = await ticket_service.resolve_ticket(db, ticket_ref)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    filename = file.filename or f"attachment_{uuid.uuid4()}"

    attachment = await attachment_service.create_attachment(
        db,
        ticket_id=ticket.id,
        uploader_id=current_user.id,
        filename=filename,
        content=content,
        mime_type=mime_type,
    )

    if not attachment:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await notification_service.broadcast_global_event(
        type=WSMessageType.TICKET_UPDATED,
        data={"id": str(ticket.id), "ticket_number": ticket.ticket_number},
        db=db,
    )
    return attachment


@router.delete(
    "/{ticket_ref}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment",
)
async def delete_attachment(
    ticket_ref: str,
    attachment_id: uuid.UUID,
    db: DB,
    current_user: CurrentUser,
):
    """Delete an attachment. Only its uploader is authorised.

    Raises:
        HTTPException: **404** if the attachment does not exist.
        HTTPException: **403** if the caller is not the uploader.
    """
    ticket = await ticket_service.resolve_ticket(db, ticket_ref)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    success = await attachment_service.delete_attachment(
        db, attachment_id=attachment_id, actor_id=current_user.id
    )
    if not success:
        # Why: the service returns False both for "not found" and "forbidden";
        # disambiguate here so the API responds with the correct status code.
        from sqlalchemy import select
        from app.models.attachment import Attachment
        exists = (await db.execute(select(Attachment).where(Attachment.id == attachment_id))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="Attachment not found")
        raise HTTPException(status_code=403, detail="You can only delete your own attachments")

    await notification_service.broadcast_global_event(
        type=WSMessageType.TICKET_UPDATED,
        data={"id": str(ticket.id), "ticket_number": ticket.ticket_number},
        db=db,
    )


@router.patch(
    "/{ticket_ref}/attachments/{attachment_id}",
    response_model=AttachmentOut,
    summary="Toggle use_for_rag for an attachment",
)
async def toggle_attachment_rag(
    ticket_ref: str,
    attachment_id: uuid.UUID,
    use_for_rag: bool,
    db: DB,
    current_user: CurrentUser,
):
    """Toggle whether an attachment is indexed by the RAG pipeline.

    When `use_for_rag` is true, the file content will be chunked and
    embedded so the AI copilot can cite it; when false, it is ignored by
    the retrieval layer (but still accessible to humans).

    Returns:
        AttachmentOut: The updated attachment.

    Raises:
        HTTPException: **404** if the attachment does not exist.
    """
    attachment = await attachment_service.update_attachment_rag(
        db, attachment_id=attachment_id, use_for_rag=use_for_rag
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment
