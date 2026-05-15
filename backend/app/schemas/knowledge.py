"""Pydantic schemas for knowledge-base ingestion."""

from pydantic import BaseModel, HttpUrl


class IngestRequest(BaseModel):
    """Body of `POST /knowledge` — the URL to scrape and index."""
    url: HttpUrl


class IngestResponse(BaseModel):
    """Response shape for `POST /knowledge`: URL plus number of chunks written."""
    url: str
    chunks_created: int
