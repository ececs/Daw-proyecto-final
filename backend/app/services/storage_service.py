"""Asynchronous S3-compatible object storage interaction engine.

Provides decoupled file upload, removal, and retrieval abstractions leveraging aiobotocore.
Facilitates offloaded client downloads by generating time-sensitive Presigned URLs,
minimizing server bandwidth exhaustion and improving overall cloud storage scaling.
"""

import uuid
from contextlib import asynccontextmanager

import aiobotocore.session
from botocore.exceptions import ClientError

from app.core.config import settings


@asynccontextmanager
async def _s3_client():
    """Yields an active, asynchronous boto3 S3-compatible client instance.

    Injects endpoint, access, and secret key values populated from local application settings.
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
    """Generates a secure, collision-resistant absolute storage key path string."""
    unique_prefix = uuid.uuid4()
    return f"tickets/{ticket_id}/{unique_prefix}/{filename}"


async def upload_file(
    ticket_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    """Uploads raw binary file byte streams to remote S3 compatible buckets.

    Args:
        ticket_id: UUID reference of the parent ticket organizing the files.
        filename: Clean base filename preserving the uploaded file extensions.
        content: Encoded binary content representing the object payload.
        mime_type: Content-Type string metadata determining web browser behavior.

    Returns:
        str: Formatted unique object storage key.
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
    """Generates a secured GET presigned URL for temporary direct browser download.

    Args:
        storage_key: Fully-qualified path to the object stored within the bucket.
        expires_in: Expiration lifespan in seconds (Defaults to 3600/1 hour).

    Returns:
        str: Signed access URL containing temporary credential signatures.
    """
    async with _s3_client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.STORAGE_BUCKET, "Key": storage_key},
            ExpiresIn=expires_in,
        )
    return url


async def download_file(storage_key: str) -> bytes:
    """Directly downloads full binary content payloads from object stores into memory.

    Primarily executed by internal background ingestion tasks bypass secondary URL hops.
    """
    async with _s3_client() as s3:
        response = await s3.get_object(Bucket=settings.STORAGE_BUCKET, Key=storage_key)
        return await response["Body"].read()


async def delete_file(storage_key: str) -> None:
    """Removes an object from the active remote bucket matching the specified key."""
    async with _s3_client() as s3:
        await s3.delete_object(Bucket=settings.STORAGE_BUCKET, Key=storage_key)
