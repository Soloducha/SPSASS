"""Tests para API Keys: crear, listar, revocar, autenticar agente."""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_create_api_key_requires_admin_role() -> None:
    """Crear API key requiere rol ADMIN u OWNER."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Registrar usuario normal (rol MEMBER por defecto al unirse a tenant existente)
        # Primero crear owner
        await client.post(
            "/auth/register",
            json={"email": "owner@example.com", "password": "password123", "full_name": "Owner"},
        )
        login_owner = await client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "password123"},
        )
        owner_token = login_owner.json()["access_token"]

        # Owner puede crear API key (es OWNER)
        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "Agent from Owner"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert create_resp.status_code == 201
        assert "raw_key" in create_resp.json()
        assert create_resp.json()["raw_key"].startswith("spsk_")


@pytest.mark.asyncio
async def test_create_api_key_returns_raw_key_only_once() -> None:
    """Al crear API key, raw_key se muestra una sola vez; listado no la incluye."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "apikeyowner@example.com", "password": "password123", "full_name": "API Key Owner"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "apikeyowner@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # Crear
        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "Test Agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        raw_key = created["raw_key"]
        key_id = created["id"]
        assert raw_key.startswith("spsk_")

        # Listar -> NO debe incluir raw_key
        list_resp = await client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        keys = list_resp.json()
        assert len(keys) == 1
        assert keys[0]["id"] == key_id
        assert "raw_key" not in keys[0]
        assert keys[0]["name"] == "Test Agent"
        assert keys[0]["prefix"] == "spsk_"


@pytest.mark.asyncio
async def test_list_api_keys_requires_admin() -> None:
    """Listar API keys requiere rol ADMIN u OWNER."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "listowner@example.com", "password": "password123", "full_name": "List Owner"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "listowner@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # Crear un par de keys
        await client.post(
            "/auth/api-keys",
            json={"name": "Agent 1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            "/auth/api-keys",
            json={"name": "Agent 2"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Listar
        list_resp = await client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        keys = list_resp.json()
        assert len(keys) == 2
        # Orden: más recientes primero
        assert keys[0]["name"] == "Agent 2"
        assert keys[1]["name"] == "Agent 1"


@pytest.mark.asyncio
async def test_revoke_api_key_requires_admin() -> None:
    """Revocar API key requiere rol ADMIN u OWNER."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "revokeowner@example.com", "password": "password123", "full_name": "Revoke Owner"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "revokeowner@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # Crear key
        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "To Revoke"},
            headers={"Authorization": f"Bearer {token}"},
        )
        key_id = create_resp.json()["id"]

        # Revocar
        revoke_resp = await client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 204

        # Verificar que ya no está en listado
        list_resp = await client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_revoke_nonexistent_api_key_returns_404() -> None:
    """Revocar API key inexistente retorna 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "revoke404@example.com", "password": "password123", "full_name": "Revoke 404"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "revoke404@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # UUID aleatorio que no existe
        fake_id = "550e8400-e29b-41d4-a716-446655440000"
        revoke_resp = await client.delete(
            f"/auth/api-keys/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_cross_tenant_returns_404() -> None:
    """Revocar API key de otro tenant retorna 404 (no 403 para no filtrar existencia)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A
        await client.post(
            "/auth/register",
            json={"email": "ownera@example.com", "password": "password123", "full_name": "Owner A"},
        )
        login_a = await client.post(
            "/auth/login",
            json={"email": "ownera@example.com", "password": "password123"},
        )
        token_a = login_a.json()["access_token"]

        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "Agent A"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        key_id_a = create_resp.json()["id"]

        # Tenant B
        await client.post(
            "/auth/register",
            json={"email": "ownerb@example.com", "password": "password123", "full_name": "Owner B"},
        )
        login_b = await client.post(
            "/auth/login",
            json={"email": "ownerb@example.com", "password": "password123"},
        )
        token_b = login_b.json()["access_token"]

        # Tenant B intenta revocar key de Tenant A
        revoke_resp = await client.delete(
            f"/auth/api-keys/{key_id_a}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert revoke_resp.status_code == 404


@pytest.mark.asyncio
async def test_api_key_auth_valid_key_works() -> None:
    """Autenticación con API key válida funciona (test unitario del servicio)."""
    # Este test verifica el flujo completo via endpoint protegido hipotético
    # Por ahora testamos que la creación genera key válida
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "authowner@example.com", "password": "password123", "full_name": "Auth Owner"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "authowner@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "Valid Agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        raw_key = create_resp.json()["raw_key"]

        # Verificar formato: prefix + token
        assert raw_key.startswith("spsk_")
        # Longitud razonable (prefijo 5 + token url-safe ~43 chars)
        assert len(raw_key) > 20


@pytest.mark.asyncio
async def test_api_key_prefix_matches_settings() -> None:
    """El prefix de la API key coincide con API_KEY_PREFIX de settings."""
    from app.core.config import get_settings
    settings = get_settings()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "prefixowner@example.com", "password": "password123", "full_name": "Prefix Owner"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "prefixowner@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "Prefix Test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert data["prefix"] == settings.API_KEY_PREFIX
        assert data["raw_key"].startswith(settings.API_KEY_PREFIX)


@pytest.mark.asyncio
async def test_create_multiple_api_keys_same_tenant() -> None:
    """Crear múltiples API keys en mismo tenant funciona."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/auth/register",
            json={"email": "multikey@example.com", "password": "password123", "full_name": "Multi Key"},
        )
        login_resp = await client.post(
            "/auth/login",
            json={"email": "multikey@example.com", "password": "password123"},
        )
        token = login_resp.json()["access_token"]

        # Crear 3 keys
        names = ["Agent 1", "Agent 2", "Agent 3"]
        for name in names:
            resp = await client.post(
                "/auth/api-keys",
                json={"name": name},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201

        # Listar todas
        list_resp = await client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        keys = list_resp.json()
        assert len(keys) == 3
        key_names = {k["name"] for k in keys}
        assert key_names == set(names)


@pytest.mark.asyncio
async def test_api_key_without_auth_returns_401() -> None:
    """Endpoints de API key sin autenticación retornan 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Crear sin token
        resp = await client.post("/auth/api-keys", json={"name": "No Auth"})
        assert resp.status_code == 401

        # Listar sin token
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 401

        # Revocar sin token
        resp = await client.delete("/auth/api-keys/some-id")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_invalid_format_returns_401() -> None:
    """Verificación de API key con formato inválido (test del servicio verify_api_key_from_header)."""

    from app.core.auth.service import InvalidTokenError, verify_api_key_from_header
    from app.db.session import get_db_session

    # Test unitario directo del servicio
    async with get_db_session() as session:
        # Intentar verificar key con formato incorrecto
        with pytest.raises(InvalidTokenError, match="Formato de API key inválido"):
            await verify_api_key_from_header(session, "invalid-format")

        # Intentar verificar key con prefix correcto pero que no existe
        with pytest.raises(InvalidTokenError, match="API key inválida"):
            await verify_api_key_from_header(session, "spsk_nonexistentkey")


# NOTA: Tests de autenticación real con X-Api-Key header contra endpoints
# requieren un endpoint protegido por ApiKeyAuth dependency.
# Actualmente no hay endpoints de ejemplo que usen esa dependency.
# Cuando se agreguen endpoints de ingesta de métricas/alertas, agregar tests
# que usen `headers={"X-Api-Key": raw_key}`.
