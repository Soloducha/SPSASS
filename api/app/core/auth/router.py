"""Router de autenticación: register, login, refresh, API keys."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.auth.dependencies import (
    CurrentTenant,
    CurrentUser,
    RequireAdmin,
    SessionDep,
    user_to_response,
)
from app.core.auth.schemas import (
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.auth.service import (
    ApiKeyNotFoundError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
    create_api_key,
    list_api_keys,
    login_user,
    refresh_access_token,
    register_user,
    revoke_api_key,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ──────────────────────────────────────────────
# Public Auth Endpoints
# ──────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    session: SessionDep,
    data: RegisterRequest,
) -> TokenResponse:
    """
    Registra un nuevo usuario y tenant.
    - Si no se provee tenant_slug, crea tenant personal (plan FREE).
    - Retorna access_token + refresh_token.
    """
    try:
        _, _, tokens = await register_user(session, data)
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        logger.exception("register_failed", email=data.email)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno") from e

    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(
    session: SessionDep,
    data: LoginRequest,
) -> TokenResponse:
    """
    Autentica usuario y retorna tokens.
    """
    try:
        return await login_user(session, data)
    except (InvalidCredentialsError, Exception) as e:
        if isinstance(e, InvalidCredentialsError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
        logger.exception("login_failed", email=data.email)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno") from e


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest,
) -> TokenResponse:
    """
    Renueva access token usando refresh token.
    """
    try:
        return await refresh_access_token(data.refresh_token)
    except InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except Exception as e:
        logger.exception("refresh_failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno") from e


# ──────────────────────────────────────────────
# Protected User Endpoints
# ──────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    """
    Obtiene información del usuario autenticado.
    """
    return user_to_response(user)


# ──────────────────────────────────────────────
# API Key Endpoints (requieren auth + admin)
# ──────────────────────────────────────────────
@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key_endpoint(
    session: SessionDep,
    user: RequireAdmin,
    tenant: CurrentTenant,
    data: ApiKeyCreateRequest,
) -> ApiKeyResponse:
    """
    Crea una nueva API key para agentes.
    Requiere rol ADMIN u OWNER en el tenant.
    **La raw_key solo se muestra UNA vez en la respuesta.**
    """
    try:
        return await create_api_key(session, tenant.id, data)
    except Exception as e:
        logger.exception("create_api_key_failed", tenant_id=str(tenant.id))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno") from e


@router.get("/api-keys", response_model=list[ApiKeyListResponse])
async def list_api_keys_endpoint(
    session: SessionDep,
    user: RequireAdmin,
    tenant: CurrentTenant,
) -> list[ApiKeyListResponse]:
    """
    Lista API keys del tenant (sin raw keys).
    Requiere rol ADMIN u OWNER.
    """
    return await list_api_keys(session, tenant.id)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key_endpoint(
    session: SessionDep,
    user: RequireAdmin,
    tenant: CurrentTenant,
    key_id: UUID,
) -> None:
    """
    Revoca (elimina) una API key.
    Requiere rol ADMIN u OWNER.
    """
    try:
        await revoke_api_key(session, tenant.id, key_id)
    except ApiKeyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.exception("revoke_api_key_failed", key_id=str(key_id))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno") from e
