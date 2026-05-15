"""User directory queries."""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.schemas.user import UserOut


async def list_users(db: AsyncSession) -> List[UserOut]:
    """Return every user ordered alphabetically by `name`.

    Returns:
        list[UserOut]: All users in the directory.
    """
    result = await db.execute(select(User).order_by(User.name))
    users = result.scalars().all()
    return [UserOut.model_validate(u) for u in users]
