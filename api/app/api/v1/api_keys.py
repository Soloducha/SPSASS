"""Router de API keys: creacion desde la web con JWT de usuario.

Replica el contrato de `POST /auth/api-keys` bajo el namespace `/api/v1`
para que el frontend web no dependa del router de auth. Delega la
generacion, hashing y persistencia en `app.core.auth.service.create_api_key`
para no duplicar reglas de seguridad.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth.dependencies import CurrentTenant, RequireAdmin, SessionDep
from app.core.auth.schemas import ApiKeyCreateRequest
from app.core.auth.service import create_api_key as service_create_api_key
from app.core.logging import get_logger
from app.models.api_key import ApiKey

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    """
    Request de creacion de API key.

    `description` se acepta por contrato de la API, pero el modelo `ApiKey`
    todavia no tiene columna que lo persista: se acepta y se descarta.
    """

    name: str = Field(min_length=1, max_length=100, description="Nombre identificador de la key")
    description: str | None = Field(default=None, max_length=500)


class ApiKeyCreatedResponse(BaseModel):
    """
    API key recien creada.

    `key` contiene la clave en claro y solo se devuelve en esta respuesta:
    en BD solo se guarda el hash.
    """

    id: UUID
    name: str
    prefix: str
    key: str
    created_at: datetime


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────
@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key_endpoint(
    session: SessionDep,
    tenant: CurrentTenant,
    data: ApiKeyCreate,
    _user: RequireAdmin,
) -> ApiKeyCreatedResponse:
    """
    Crea una API key para el tenant del usuario autenticado.

    Requiere rol ADMIN u OWNER. El nombre es unico por tenant
    (uq_api_key_tenant_name): un duplicado devuelve 409.
    **La clave en claro (`key`) solo se muestra UNA vez, aqui.**
    """
    # Pre-check del duplicado: el unique constraint solo se manifiesta en el
    # commit del service, y para entonces la session async ya quedo envenenada
    # (PendingRollbackError). uq_api_key_tenant_name hace este SELECT barato.
    existing = await session.execute(
        select(ApiKey.id).where(
            ApiKey.tenant_id == tenant.id,
            ApiKey.name == data.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        logger.warning(
            "api_key_duplicate_name",
            tenant_id=str(tenant.id),
            name=data.name,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una API key llamada '{data.name}'",
        )

    try:
        created = await service_create_api_key(
            session,
            tenant.id,
            ApiKeyCreateRequest(name=data.name),
        )
    except IntegrityError as e:
        # Carrera con otra peticion concurrente: la session ya esta envenenada,
        # asi que no se intenta rollback aqui. La dependencia de session la
        # descarta al cerrar el request.
        logger.warning(
            "api_key_duplicate_name_race",
            tenant_id=str(tenant.id),
            name=data.name,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una API key llamada '{data.name}'",
        ) from e

    return ApiKeyCreatedResponse(
        id=created.id,
        name=created.name,
        prefix=created.prefix,
        key=created.raw_key,
        created_at=created.created_at,
    )
