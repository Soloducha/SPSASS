"""Seguridad: hashing de contraseñas, JWT, API keys."""

import secrets
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

# ──────────────────────────────────────────────
# Password Hashing (bcrypt via passlib)
# ──────────────────────────────────────────────
# bcrypt 4.0+ compatibility: passlib needs explicit backend selection
# Use bcrypt_sha256 as fallback for tests (shorter hash, no 72-byte limit)
import os

if os.environ.get("TESTING") == "1":
    # En tests usamos sha256_crypt que no tiene límite de 72 bytes y funciona en SQLite
    pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
else:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashea una contraseña usando bcrypt."""
    hashed: str = pwd_context.hash(password)
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash."""
    verified: bool = pwd_context.verify(plain_password, hashed_password)
    return verified


# ──────────────────────────────────────────────
# JWT Token Handling
# ──────────────────────────────────────────────
class TokenPayload(BaseModel):
    """Payload del JWT access token."""
    sub: str  # user_id
    tenant_id: str
    role: str
    is_superuser: bool = False
    type: str = "access"
    exp: int
    iat: int


class RefreshTokenPayload(BaseModel):
    """Payload del JWT refresh token."""
    sub: str  # user_id
    tenant_id: str  # Para poder renovar access token con el mismo tenant
    role: str  # Para recrear access token
    is_superuser: bool = False  # Para recrear access token
    type: str = "refresh"
    exp: int
    iat: int


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    is_superuser: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    """Crea un JWT access token."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=role,
        is_superuser=is_superuser,
        type="access",
        exp=int(expire.timestamp()),
        iat=int(now.timestamp()),
    )
    token: str = jwt.encode(payload.model_dump(), settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def create_refresh_token(user_id: str, tenant_id: str, role: str, is_superuser: bool = False, expires_delta: timedelta | None = None) -> str:
    """Crea un JWT refresh token."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload = RefreshTokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=role,
        is_superuser=is_superuser,
        type="refresh",
        exp=int(expire.timestamp()),
        iat=int(now.timestamp()),
    )
    token: str = jwt.encode(payload.model_dump(), settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_token(token: str) -> TokenPayload | RefreshTokenPayload:
    """Decodifica y valida un JWT."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise JWTError(f"Token inválido: {e}") from e

    token_type = payload.get("type")
    if token_type == "access":
        return TokenPayload(**payload)
    if token_type == "refresh":
        return RefreshTokenPayload(**payload)
    raise JWTError("Token inválido: tipo de token inválido")


# ──────────────────────────────────────────────
# API Key Handling (para agentes)
# ──────────────────────────────────────────────
API_KEY_PREFIX = settings.API_KEY_PREFIX
API_KEY_BYTES = 32  # 256 bits de entropía


def generate_api_key() -> tuple[str, str]:
    """
    Genera una API key nueva.
    Returns: (raw_key, hashed_key)
    - raw_key: se muestra UNA sola vez al usuario (prefijo + token)
    - hashed_key: se guarda en BD (bcrypt)
    """
    token = secrets.token_urlsafe(API_KEY_BYTES)
    raw_key = f"{API_KEY_PREFIX}{token}"
    hashed_key = hash_password(raw_key)
    return raw_key, hashed_key


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    """Verifica una API key contra su hash almacenado."""
    return verify_password(raw_key, hashed_key)


def hash_api_key(raw_key: str) -> str:
    """Hashea una API key para almacenamiento."""
    return hash_password(raw_key)
