"""Declarative base for every ORM model in the project."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared `DeclarativeBase` — every `app.models.*` table inherits from this."""
    pass
