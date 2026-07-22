"""Current-user profile (`GET /api/me`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.users import MeOut
from app.services import users

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
async def read_me(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MeOut:
    user = await users.get(db, cu.user_id)
    return MeOut.model_validate(user)
