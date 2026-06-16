"""FastAPI зависимость для Bearer-аутентификации внутри auth-svc.

Используется на /cli/code и /cli/device-approve — клиент должен быть
аутентифицирован (после magic-link verify он получил access_token).
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.deps import SessionDep
from auth_service.jwt_signer import verify_access_token
from auth_service.models import User


async def get_authenticated_user(request: Request, session: SessionDep) -> User:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer token required"
        )
    token = auth_header[7:].strip()
    try:
        claims = verify_access_token(token)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}"
        ) from e
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing sub claim"
        )
    user = await _find_user(session, sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found"
        )
    return user


async def _find_user(session: AsyncSession, user_id_str: str) -> User | None:
    if not user_id_str or len(user_id_str) != 40:
        return None
    result = await session.execute(select(User).where(User.id == user_id_str))
    return result.scalar_one_or_none()


AuthenticatedUserDep = Annotated[User, Depends(get_authenticated_user)]
