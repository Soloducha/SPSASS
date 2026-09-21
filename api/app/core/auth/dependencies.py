"""Dependencias FastAPI para auth y RBAC."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.schemas import UserResponse
from app.core.auth.security import decode_token
from app.core.auth.service import (
    InvalidTokenError,
    get_current_user as service_get_current_user,
    verify_api_key_from_header,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db_session
from app.models.tenant import Tenant
from app.models.user import User, UserRole

logger = get_logger(__name__)
settings = get_settings()


# ──────────────────────────────────────────────
# Database Session Dependency
# ──────────────────────────────────────────────
async def get_session() -> AsyncSession:
    """Dependencia para obtener sesión de BD."""
    async with get_db_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ──────────────────────────────────────────────
# JWT Auth Dependencies
# ──────────────────────────────────────────────
async def get_current_user(
    session: SessionDep,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    """
    Dependencia que obtiene el usuario actual desde JWT Bearer token.
    Header: Authorization: Bearer <access_token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]  # Quitar "Bearer "

    try:
        user = await service_get_current_user(session, token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    session: SessionDep,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User | None:
    """Como get_current_user pero retorna None si no hay token (para endpoints opcionales)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    try:
        return await service_get_current_user(session, token)
    except InvalidTokenError:
        return None


OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


# ──────────────────────────────────────────────
# RBAC Dependencies
# ──────────────────────────────────────────────
def require_role(*allowed_roles: UserRole):
    """
    Dependencia factory que requiere uno de los roles permitidos.
    Uso: `Depends(require_role(UserRole.ADMIN, UserRole.OWNER))`
    """
    async def role_checker(user: CurrentUser) -> User:
        # Superuser bypassa todo
        if user.is_superuser:
            return user

        if user.role not in allowed_roles:
            logger.warning(
                "rbac_denied",
                user_id=str(user.id),
                required_roles=[r.value for r in allowed_roles],
                user_role=user.role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {[r.value for r in allowed_roles]}",
            )
        return user

    return role_checker


RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.OWNER))]
RequireOwner = Annotated[User, Depends(require_role(UserRole.OWNER))]
RequireMember = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.OWNER, UserRole.MEMBER))]


# ──────────────────────────────────────────────
# Tenant Dependencies
# ──────────────────────────────────────────────
async def get_current_tenant(
    session: SessionDep,
    user: CurrentUser,
) -> Tenant:
    """
    Obtiene el tenant del usuario actual (desde JWT).
    El tenant_id viene en el token, verificamos que exista.
    """
    from sqlalchemy import select

    result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado",
        )

    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


# ──────────────────────────────────────────────
# API Key Dependencies (para agentes)
# ──────────────────────────────────────────────
async def get_tenant_from_api_key(
    session: SessionDep,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> tuple[Tenant, str]:
    """
    Dependencia para autenticar agentes via API Key.
    Header: X-Api-Key: spsk_<token>
    Retorna (tenant, api_key_name)
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Api-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    try:
        tenant, api_key = await verify_api_key_from_header(session, x_api_key)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "ApiKey"},
        ) from e

    return tenant, api_key.name


ApiKeyAuth = Annotated[tuple[Tenant, str], Depends(get_tenant_from_api_key)]


# ──────────────────────────────────────────────
# Current User Response Schema
# ──────────────────────────────────────────────
def user_to_response(user: User) -> UserResponse:
    """Convierte modelo User a schema de respuesta."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        tenant_id=user.tenant_id,
        created_at=user.created_at,
    )