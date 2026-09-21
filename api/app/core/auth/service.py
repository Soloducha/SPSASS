"""Lógica de negocio de auth: registro, login, API keys."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    verify_password,
)
from app.core.auth.schemas import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    ApiKeyListResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole

logger = get_logger(__name__)
settings = get_settings()


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────
class AuthError(Exception):
    """Error base de autenticación."""
    pass


class InvalidCredentialsError(AuthError):
    """Credenciales inválidas."""
    pass


class UserAlreadyExistsError(AuthError):
    """Usuario ya existe."""
    pass


class UserNotFoundError(AuthError):
    """Usuario no encontrado."""
    pass


class TenantNotFoundError(AuthError):
    """Tenant no encontrado."""
    pass


class InactiveUserError(AuthError):
    """Usuario inactivo."""
    pass


class InvalidTokenError(AuthError):
    """Token inválido o expirado."""
    pass


class ApiKeyNotFoundError(AuthError):
    """API key no encontrada."""
    pass


# ──────────────────────────────────────────────
# User Auth Service
# ──────────────────────────────────────────────
async def register_user(
    session: AsyncSession,
    data: RegisterRequest,
) -> tuple[User, Tenant, TokenResponse]:
    """
    Registra un nuevo usuario.
    Si no existe tenant_slug, crea tenant personal (plan FREE).
    Retorna (user, tenant, tokens).
    """
    # Verificar si email ya existe
    existing = await session.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise UserAlreadyExistsError(f"Email {data.email} ya registrado")

    # Buscar o crear tenant
    if data.tenant_slug:
        tenant_result = await session.execute(select(Tenant).where(Tenant.slug == data.tenant_slug))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundError(f"Tenant '{data.tenant_slug}' no existe")
    else:
        # Crear tenant personal con slug basado en email
        base_slug = data.email.split("@")[0].lower().replace(".", "-")
        slug = base_slug
        counter = 1
        while True:
            existing_tenant = await session.execute(select(Tenant).where(Tenant.slug == slug))
            if not existing_tenant.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = Tenant(name=data.full_name or data.email.split("@")[0], slug=slug)
        session.add(tenant)
        await session.flush()

    # Crear usuario como owner del tenant
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        tenant_id=tenant.id,
        full_name=data.full_name,
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    # Crear tenant_members entry
    from app.models.tenant_member import TenantMember, MemberRole

    member = TenantMember(user_id=user.id, tenant_id=tenant.id, role=MemberRole.OWNER)
    session.add(member)
    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)

    # Generar tokens
    access_token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role.value,
        is_superuser=user.is_superuser,
    )
    refresh_token = create_refresh_token(user_id=str(user.id))

    logger.info("user_registered", user_id=str(user.id), tenant_id=str(tenant.id), email=data.email)

    return user, tenant, TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def login_user(session: AsyncSession, data: LoginRequest) -> TokenResponse:
    """Autentica usuario y retorna tokens."""
    result = await session.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        logger.warning("login_failed", email=data.email, reason="invalid_credentials")
        raise InvalidCredentialsError("Credenciales inválidas")

    if not user.is_active:
        logger.warning("login_failed", email=data.email, reason="inactive_user")
        raise InactiveUserError("Usuario inactivo")

    # Actualizar last_login
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    access_token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role.value,
        is_superuser=user.is_superuser,
    )
    refresh_token = create_refresh_token(user_id=str(user.id))

    logger.info("user_logged_in", user_id=str(user.id), tenant_id=str(user.tenant_id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def refresh_access_token(refresh_token: str) -> TokenResponse:
    """Genera nuevo access token desde refresh token."""
    try:
        payload = decode_token(refresh_token)
        if payload.type != "refresh":
            raise InvalidTokenError("Token no es un refresh token")
    except Exception as e:
        raise InvalidTokenError(f"Refresh token inválido: {e}") from e

    # Verificar que el usuario existe y está activo
    from app.db.session import get_db_session

    async with get_db_session() as session:
        result = await session.execute(
            select(User).where(User.id == UUID(payload.sub))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise InvalidTokenError("Usuario no encontrado o inactivo")

    access_token = create_access_token(
        user_id=payload.sub,
        tenant_id=payload.tenant_id,
        role=payload.role,
        is_superuser=payload.is_superuser,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,  # Reutilizar mismo refresh token
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def get_current_user(session: AsyncSession, token: str) -> User:
    """Obtiene usuario actual desde access token."""
    try:
        payload = decode_token(token)
        if payload.type != "access":
            raise InvalidTokenError("Token no es un access token")
    except Exception as e:
        raise InvalidTokenError(f"Token inválido: {e}") from e

    result = await session.execute(
        select(User).where(User.id == UUID(payload.sub))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise InvalidTokenError("Usuario no encontrado o inactivo")

    return user


# ──────────────────────────────────────────────
# API Key Service (para agentes)
# ──────────────────────────────────────────────
async def create_api_key(
    session: AsyncSession,
    tenant_id: UUID,
    data: ApiKeyCreateRequest,
) -> ApiKeyResponse:
    """Crea una nueva API key para un tenant."""
    raw_key, hashed_key = generate_api_key()

    api_key = ApiKey(
        tenant_id=tenant_id,
        name=data.name,
        key_hash=hashed_key,
        prefix=settings.API_KEY_PREFIX,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    logger.info("api_key_created", api_key_id=str(api_key.id), tenant_id=str(tenant_id), name=data.name)

    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        raw_key=raw_key,  # Solo se muestra aquí
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
    )


async def list_api_keys(session: AsyncSession, tenant_id: UUID) -> list[ApiKeyListResponse]:
    """Lista API keys de un tenant (sin raw keys)."""
    result = await session.execute(
        select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [
        ApiKeyListResponse(
            id=k.id,
            name=k.name,
            prefix=k.prefix,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


async def revoke_api_key(session: AsyncSession, tenant_id: UUID, key_id: UUID) -> None:
    """Revoca (elimina) una API key."""
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise ApiKeyNotFoundError("API key no encontrada")

    await session.delete(api_key)
    await session.commit()

    logger.info("api_key_revoked", api_key_id=str(key_id), tenant_id=str(tenant_id))


async def verify_api_key_from_header(session: AsyncSession, raw_key: str) -> tuple[Tenant, ApiKey]:
    """
    Verifica API key desde header X-Api-Key.
    Retorna (tenant, api_key) si válida.
    """
    if not raw_key.startswith(settings.API_KEY_PREFIX):
        raise InvalidTokenError("Formato de API key inválido")

    # Buscar por prefijo (optimización: podríamos indexar por hash pero bcrypt no permite)
    # Para MVP, iteramos las keys del tenant - en producción usar lookup por hash parcial
    result = await session.execute(select(ApiKey).where(ApiKey.prefix == settings.API_KEY_PREFIX))
    keys = result.scalars().all()

    for key in keys:
        if verify_password(raw_key, key.key_hash):
            # Actualizar last_used_at
            key.last_used_at = datetime.now(UTC)
            await session.commit()

            # Cargar tenant
            tenant_result = await session.execute(select(Tenant).where(Tenant.id == key.tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                raise InvalidTokenError("Tenant asociado no encontrado")

            return tenant, key

    raise InvalidTokenError("API key inválida")