"""Router de invitaciones a tenant (T2 - Mes 6).

Flujo completo:
1. Un admin del tenant crea la invitacion (`POST /api/v1/invitations`), que
   genera un JWT `type="invitation"` y lo manda por email.
2. La persona abre el link, elige contrasena y la acepta
   (`POST /api/v1/invitations/accept/{token}`, publico).
3. La aceptacion crea el usuario si no existe, agrega la membresia al tenant y
   devuelve tokens de sesion equivalentes a un login/registro.

El token de invitacion se firma con el mismo secreto y algoritmo que los access
tokens, pero **no** se emite con `create_access_token`: ese helper construye un
`TokenPayload` fijo (`type="access"`) y `decode_token` rechaza cualquier tipo
distinto. Por eso los helpers de abajo son explicitos sobre su payload.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
)
from app.core.auth.dependencies import CurrentTenant, RequireAdmin, SessionDep, user_to_response
from app.core.auth.schemas import TenantResponse
from app.core.auth.security import create_access_token, create_refresh_token, hash_password
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.plan import guard_invitation_creation
from app.models.tenant import Tenant
from app.models.tenant_invitation import TenantInvitation
from app.models.tenant_member import MemberRole, TenantMember
from app.models.user import User, UserRole
from app.workers.delivery.invitation_email import InvitationEmailError, send_invitation_email

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])

INVITATION_TOKEN_TYPE = "invitation"

_MEMBER_TO_USER_ROLE: dict[MemberRole, UserRole] = {
    MemberRole.OWNER: UserRole.OWNER,
    MemberRole.ADMIN: UserRole.ADMIN,
    MemberRole.MEMBER: UserRole.MEMBER,
    MemberRole.VIEWER: UserRole.VIEWER,
}


# ──────────────────────────────────────────────
# Token de invitacion
# ──────────────────────────────────────────────
class InvitationTokenPayload(BaseModel):
    """Claims del JWT de invitacion (`sub` es el email invitado)."""

    email: str
    tenant_id: UUID
    role: MemberRole


class InvalidInvitationTokenError(ValueError):
    """El token no es un JWT de invitacion valido."""


def create_invitation_token(
    *,
    email: str,
    tenant_id: UUID,
    role: MemberRole,
    expires_at: datetime,
) -> str:
    """Genera el JWT `type="invitation"` que viaja en el link del email."""
    now = datetime.now(UTC)
    payload = {
        "sub": email,
        "tenant_id": str(tenant_id),
        "role": role.value,
        "type": INVITATION_TOKEN_TYPE,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
    }
    token: str = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_invitation_token(token: str) -> InvitationTokenPayload:
    """Valida firma, expiracion y `type` del token de invitacion."""
    try:
        claims: dict = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise InvalidInvitationTokenError(
            "La invitacion es invalida o ya expiro. Pide una nueva al administrador."
        ) from exc

    if claims.get("type") != INVITATION_TOKEN_TYPE:
        raise InvalidInvitationTokenError("El enlace no corresponde a una invitacion.")

    try:
        return InvitationTokenPayload(
            email=str(claims["sub"]),
            tenant_id=UUID(str(claims["tenant_id"])),
            role=MemberRole(str(claims["role"])),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidInvitationTokenError("La invitacion tiene un formato invalido.") from exc


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _build_accept_url(token: str) -> str:
    """Link web de aceptacion de la invitacion."""
    return f"{settings.WEB_URL.rstrip('/')}/accept-invitation/{token}"


async def _get_pending_invitation(
    session: AsyncSession, token: str, claims: InvitationTokenPayload
) -> TenantInvitation:
    """Carga la invitacion pendiente asociada al token o responde 4xx."""
    result = await session.execute(
        select(TenantInvitation).where(TenantInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitacion no encontrada",
        )
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Esta invitacion ya fue aceptada",
        )
    if invitation.is_expired:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Esta invitacion expiro. Pide una nueva al administrador.",
        )
    if invitation.tenant_id != claims.tenant_id or invitation.email != claims.email:
        # Firma valida pero claims que no coinciden con la fila: no es
        # interpretable, se trata como token invalido en lugar de aceptarlo.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La invitacion no coincide con el enlace recibido",
        )

    return invitation


async def _get_tenant_or_404(session: AsyncSession, tenant_id: UUID) -> TenantResponse:
    """Carga el tenant invitado y lo serializa."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El tenant de la invitacion ya no existe",
        )
    return TenantResponse.model_validate(tenant)


async def _ensure_not_already_member(session: AsyncSession, user: User, tenant_id: UUID) -> None:
    """409 si el usuario ya es miembro del tenant invitado."""
    result = await session.execute(
        select(TenantMember.id).where(
            TenantMember.user_id == user.id,
            TenantMember.tenant_id == tenant_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este usuario ya es miembro del tenant",
        )


async def _find_or_create_user(
    session: AsyncSession, invitation: TenantInvitation, data: AcceptInvitationRequest
) -> tuple[User, bool]:
    """Devuelve (user, created). Crea la cuenta si el email es nuevo."""
    result = await session.execute(select(User).where(User.email == invitation.email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user, False

    new_user = User(
        email=invitation.email,
        password_hash=hash_password(data.password),
        tenant_id=invitation.tenant_id,
        full_name=data.full_name,
        role=_MEMBER_TO_USER_ROLE[invitation.role],
        is_active=True,
    )
    session.add(new_user)
    await session.flush()
    return new_user, True


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────
@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    session: SessionDep,
    tenant: CurrentTenant,
    data: InvitationCreateRequest,
    admin: RequireAdmin,
) -> InvitationResponse:
    """
    Invita a un miembro al tenant del usuario autenticado.

    Requiere rol ADMIN u OWNER. Solo puede existir una invitacion *pendiente*
    por (tenant, email): un duplicado devuelve 409.

    El `token` se devuelve siempre para que el admin pueda compartir el link a
    mano si el envio por email falla (SMTP sin configurar en dev, por ejemplo).
    """
    email = str(data.email).lower()

    # Plan Gate: validar límite de miembros antes de invitar
    await guard_invitation_creation(session, tenant)

    # Pre-check del duplicado: el indice parcial uq_tenant_invitation_pending
    # solo se manifiesta en el commit, y para entonces la session async ya
    # quedo envenenada (PendingRollbackError). Este SELECT lo evita.
    pending = await session.execute(
        select(TenantInvitation.id).where(
            TenantInvitation.tenant_id == tenant.id,
            TenantInvitation.email == email,
            TenantInvitation.accepted_at.is_(None),
        )
    )
    if pending.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay una invitacion pendiente para {email}",
        )

    expires_at = datetime.now(UTC) + timedelta(days=settings.INVITATION_EXPIRE_DAYS)
    token = create_invitation_token(
        email=email, tenant_id=tenant.id, role=data.role, expires_at=expires_at
    )

    invitation = TenantInvitation(
        tenant_id=tenant.id,
        email=email,
        role=data.role,
        token=token,
        expires_at=expires_at,
        invited_by_id=admin.id,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)

    # El email es best-effort: la invitacion ya quedo persistida y el token
    # vuelve en la respuesta, así que un fallo de SMTP no la invalida.
    try:
        await send_invitation_email(
            to_email=email,
            tenant_name=tenant.name,
            accept_url=_build_accept_url(token),
            role=data.role,
            inviter_name=admin.full_name,
        )
    except InvitationEmailError as exc:
        logger.warning(
            "invitation_created_without_email",
            invitation_id=str(invitation.id),
            tenant_id=str(tenant.id),
            to=email,
            error=str(exc),
        )

    logger.info(
        "invitation_created",
        invitation_id=str(invitation.id),
        tenant_id=str(tenant.id),
        invited_by=str(admin.id),
        to=email,
        role=data.role.value,
    )

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        token=invitation.token,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
    )


@router.get("", response_model=list[InvitationListResponse])
async def list_invitations(
    session: SessionDep,
    tenant: CurrentTenant,
    _admin: RequireAdmin,
) -> list[InvitationListResponse]:
    """Lista las invitaciones del tenant (sin token)."""
    result = await session.execute(
        select(TenantInvitation)
        .where(TenantInvitation.tenant_id == tenant.id)
        .order_by(TenantInvitation.created_at.desc())
    )
    invitations = result.scalars().all()

    return [
        InvitationListResponse(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            accepted_at=invitation.accepted_at,
        )
        for invitation in invitations
    ]


@router.post("/accept/{token}", response_model=AcceptInvitationResponse)
async def accept_invitation(
    session: SessionDep,
    token: str,
    data: AcceptInvitationRequest,
) -> AcceptInvitationResponse:
    """
    Acepta una invitacion (endpoint publico, no requiere auth).

    Crea el usuario si el email todavia no existe y lo agrega como miembro del
    tenant invitado con el rol de la invitacion. Los tokens devueltos estan
    scopeados al tenant invitado, no al tenant principal del usuario.
    """
    try:
        claims = decode_invitation_token(token)
    except InvalidInvitationTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    invitation = await _get_pending_invitation(session, token, claims)
    tenant_response = await _get_tenant_or_404(session, invitation.tenant_id)

    user, created = await _find_or_create_user(session, invitation, data)
    if not created:
        await _ensure_not_already_member(session, user, invitation.tenant_id)

    session.add(
        TenantMember(
            user_id=user.id,
            tenant_id=invitation.tenant_id,
            role=invitation.role,
        )
    )
    invitation.accepted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "invitation_accepted",
        invitation_id=str(invitation.id),
        tenant_id=str(invitation.tenant_id),
        user_id=str(user.id),
        created_user=created,
    )

    return AcceptInvitationResponse(
        access_token=create_access_token(
            user_id=str(user.id),
            tenant_id=str(invitation.tenant_id),
            role=user.role.value,
            is_superuser=user.is_superuser,
        ),
        refresh_token=create_refresh_token(
            user_id=str(user.id),
            tenant_id=str(invitation.tenant_id),
            role=user.role.value,
            is_superuser=user.is_superuser,
        ),
        user=user_to_response(user),
        tenant=tenant_response,
    )
