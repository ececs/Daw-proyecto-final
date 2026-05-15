"""S3-compatible object storage client.

Async helpers around `aiobotocore` for uploading, downloading, deleting
and generating presigned URLs against any S3-compatible backend (Amazon
S3, MinIO, Backblaze B2, ...). Used by the attachments pipeline.
"""

import uuid
from contextlib import asynccontextmanager

import aiobotocore.session
from botocore.exceptions import ClientError

from app.core.config import settings


@asynccontextmanager
async def _s3_client():
    """Yield a configured async S3 client built from `settings`.

    The credentials and endpoint come from environment-driven `settings`
    so swapping between MinIO (local dev), Amazon S3 and a self-hosted
    backend requires no code change.
    """
    session = aiobotocore.session.get_session()
    async with session.create_client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    ) as client:
        yield client


def _make_storage_key(ticket_id: uuid.UUID, filename: str) -> str:
    """Build a collision-resistant object key.

    Layout: ``tickets/<ticket_id>/<random-uuid>/<filename>``. The random
    prefix guarantees uniqueness even if the same filename is uploaded
    twice on the same ticket.
    """
    unique_prefix = uuid.uuid4()
    return f"tickets/{ticket_id}/{unique_prefix}/{filename}"


async def upload_file(
    ticket_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    """Upload `content` and return the generated storage key.

    Args:
        ticket_id: Owning ticket.
        filename: Original filename (preserved verbatim in the key for
            human readability).
        content: Raw bytes to store.
        mime_type: `Content-Type` written into the object metadata so
            browsers render it correctly when accessed via the presigned
            URL.
    """
    key = _make_storage_key(ticket_id, filename)
    async with _s3_client() as s3:
        await s3.put_object(
            Bucket=settings.STORAGE_BUCKET,
            Key=key,
            Body=content,
            ContentType=mime_type,
        )
    return key


async def get_presigned_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a time-limited GET URL for direct browser download.

    Args:
        storage_key: Key returned by `upload_file`.
        expires_in: Lifetime of the URL in seconds (default: 1 hour).
    """
    async with _s3_client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.STORAGE_BUCKET, "Key": storage_key},
            ExpiresIn=expires_in,
        )
    return url


async def download_file(storage_key: str) -> bytes:
    """Read the full object content into memory.

    Used by background ingestion jobs that need the raw bytes; clients
    should normally fetch the file via `get_presigned_url` instead.
    """
    async with _s3_client() as s3:
        response = await s3.get_object(Bucket=settings.STORAGE_BUCKET, Key=storage_key)
        return await response["Body"].read()


async def delete_file(storage_key: str) -> None:
    """Delete the object identified by `storage_key`."""
    async with _s3_client() as s3:
        await s3.delete_object(Bucket=settings.STORAGE_BUCKET, Key=storage_key)
