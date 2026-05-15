"""Database base mapping architecture.

Defines the SQLAlchemy DeclarativeBase parent from which all application ORM
models must inherit to enable declarative mapping metadata discovery.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative parent class for SQLAlchemy ORM database models.

    Aggregates model class metadata ensuring consistent registry and schema reflection.
    """
    pass
