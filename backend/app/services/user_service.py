"""User account orchestration service.

Provides querying capabilities for extracting user profile distributions
scoped through standard database transactional context.
"""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.schemas.user import UserOut

async def list_users(db: AsyncSession) -> List[UserOut]:
    """Retrieves a complete enumeration of user identities sorted alphabetically.

    Args:
        db: Active asynchronous SQLAlchemy transactional database session.

    Returns:
        List[UserOut]: A list of validated, serialized output user schemas.
    """
    result = await db.execute(select(User).order_by(User.name))
    users = result.scalars().all()
    return [UserOut.model_validate(u) for u in users]
