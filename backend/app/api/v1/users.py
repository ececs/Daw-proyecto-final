"""User directory API endpoints.

Provides validated client access to enterprise personnel listings and role structures.
Requires valid active JWT sessions for all retrieval operations.
"""

from typing import List
from fastapi import APIRouter
from app.core.dependencies import CurrentUser, DB
from app.schemas.user import UserOut
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserOut], summary="List all users")
async def list_users(current_user: CurrentUser, db: DB):
    """Fetches alphabetical listings of all registered system operators.

    Access requires a verified Bearer token issued during authentication cycles.

    Returns:
        List[UserOut]: Comprehensive enumeration of active user metadata structures.
    """
    return await user_service.list_users(db)
