#!/usr/bin/env python
"""
E2E test for auto-restart using real Docker stack.

Este test valida el flujo completo:
1. Registrar usuario y crear API key
2. Registrar server (simula agente)
3. Crear servicio con auto_restart=true
4. Poner servicio en STOPPED
5. Crear regla de alerta SERVICE
6. Ejecutar worker -> debe encolar comando auto-restart
7. Simular agente: poll /commands -> ejecutar restart -> reportar resultado
8. Verificar que servicio vuelve a RUNNING

Requiere: docker-compose up -d corriendo (api, db, redis, worker, web)
"""

import asyncio
import httpx
from uuid import UUID
from datetime import UTC, datetime


API_URL = "http://localhost:8000"


async def register_and_login(client: httpx.AsyncClient, email: str) -> str:
    """Registra usuario, hace login y retorna access_token."""
    await client.post(
        f"{API_URL}/auth/register",
        json={"email": email, "password": "password123", "full_name": email.split("@")[0]},
    )
    login_resp = await client.post(
        f"{API_URL}/auth/login",
        json={"email": email, "password": "password123"},
    )
    login_resp.raise_for_status()
    return login_resp.json()["access_token"]


async def create_api_key(client: httpx.AsyncClient, token: str, name: str) -> str:
    """Crea API key y retorna raw_key."""
    resp = await client.post(
        f"{API_URL}/auth/api-keys",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["raw_key"]


async def create_server_via_api(client: httpx.AsyncClient, api_key: str, hostname: str) -> str:
    """Registra un server y retorna su ID."""
    resp = await client.post(
        f"{API_URL}/api/v1/servers/register",
        json={"hostname": hostname},
        headers={"X-Api-Key": api_key},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def create_service_via_api(
    client: httpx.AsyncClient, token: str, server_id: str, name: str, auto_restart: bool = True
) -> str:
    """Crea un servicio via API y retorna su ID."""
    resp = await client.post(
        f"{API_URL}/api/v1/services",
        json={"server_id": server_id, "name": name, "desired_state": "running", "auto_restart": auto_restart},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def update_service_status_via_ingest(
    client: httpx.AsyncClient, api_key: str, server_id: str, service_name: str, state: str
) -> None:
    """Actualiza estado de servicio via ingesta (simula agente reportando)."""
    resp = await client.post(
        f"{API_URL}/api/v1/ingest/entities",
        json={
            "server_id": server_id,
            "services": [{"name": service_name, "state": state}],
            "processes": [],
        },
        headers={"X-Api-Key": api_key},
    )
    resp.raise_for_status()


async def create_alert_rule_via_api(
    client: httpx.AsyncClient, token: str, server_id: str, service_id: str
) -> str:
    """Crea regla de alerta SERVICE y retorna rule_id."""
    resp = await client.post(
        f"{API_URL}/api/v1/alerts/rules",
        json={
            "entity_type": "service",
            "entity_id": service_id,
            "metric": "service_status",
            "operator": "neq",
            "threshold": 0,
            "duration_s": 60,
            "severity": "warning",
            "channels": {"email": {"to": ["test@example.com"]}},
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def wait_for_worker_cycle(seconds: int = 70) -> None:
    """Espera a que el worker arq complete un ciclo (corre cada minuto)."""
    print(f"   Esperando {seconds}s para ciclo worker arq...")
    await asyncio.sleep(seconds)


async def enqueue_restart_via_api(
    client: httpx.AsyncClient, token: str, server_id: str, entity_type: str, entity_name: str
) -> dict:
    """Encola comando de restart."""
    resp = await client.post(
        f"{API_URL}/api/v1/servers/{server_id}/restart",
        json={"entity_type": entity_type, "entity_name": entity_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def list_pending_commands(client: httpx.AsyncClient, api_key: str, server_id: str) -> list:
    """Lista comandos pendientes para un server (polling agente)."""
    resp = await client.get(
        f"{API_URL}/api/v1/servers/{server_id}/commands",
        headers={"X-Api-Key": api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def report_command_result(
    client: httpx.AsyncClient, api_key: str, command_id: str, status: str, exit_code: int = 0, output_tail: str = ""
) -> dict:
    """Reporta resultado de ejecucion de comando."""
    resp = await client.patch(
        f"{API_URL}/api/v1/servers/agent-commands/{command_id}/result",
        json={"status": status, "exit_code": exit_code, "output_tail": output_tail},
        headers={"X-Api-Key": api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def get_service_status(client: httpx.AsyncClient, token: str, service_id: str) -> dict:
    """Obtiene estado de un servicio."""
    resp = await client.get(
        f"{API_URL}/api/v1/services/{service_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def main():
    print("Iniciando E2E Auto-restart test contra Docker stack real...")
    print(f"   API: {API_URL}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Registrar usuario y login
        print("\n1. Registrando usuario y login...")
        email = f"e2e_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}@example.com"
        token = await register_and_login(client, email)
        print("   OK: Token obtenido")
        
        # 2. Crear API key
        print("\n2. Creando API key...")
        api_key = await create_api_key(client, token, "E2E Agent")
        print("   OK: API key creada")
        
        # 3. Registrar server (simula agente)
        print("\n3. Registrando server (simula agente)...")
        server_id = await create_server_via_api(client, api_key, "e2e-auto-restart-server")
        print(f"   OK: Server ID: {server_id}")
        
        # 4. Crear servicio con auto_restart=true
        print("\n4. Creando servicio 'nginx' con auto_restart=true...")
        service_id = await create_service_via_api(client, token, server_id, "nginx", auto_restart=True)
        print(f"   OK: Service ID: {service_id}")
        
        # 5. Verificar estado inicial RUNNING
        print("\n5. Verificando estado inicial del servicio...")
        service = await get_service_status(client, token, service_id)
        print(f"   Estado inicial: {service.get('last_status', 'unknown')}")
        assert service.get("desired_state") == "running"
        assert service.get("auto_restart") is True
        
        # 6. Poner servicio en STOPPED (simula caida)
        print("\n6. Simulando caida del servicio (STOPPED)...")
        await update_service_status_via_ingest(client, api_key, server_id, "nginx", "stopped")
        await asyncio.sleep(1)
        service = await get_service_status(client, token, service_id)
        print(f"   Estado tras caida: {service.get('last_status', 'unknown')}")
        assert service.get("last_status") == "stopped"
        
        # 7. Crear regla de alerta SERVICE
        print("\n7. Creando regla de alerta para servicio...")
        rule_id = await create_alert_rule_via_api(client, token, server_id, service_id)
        print(f"   OK: Rule ID: {rule_id}")
        
        # 8. Esperar worker (arq corre cada minuto)
        print("\n8. Esperando ciclo worker arq (60s)...")
        await wait_for_worker_cycle(70)
        
        # 9. Verificar que se encolo comando auto-restart (polling agente)
        print("\n9. Verificando comando auto-restart encolado (polling agente)...")
        commands = await list_pending_commands(client, api_key, server_id)
        print(f"   Comandos pendientes: {len(commands)}")
        assert len(commands) == 1, f"Esperaba 1 comando, got {len(commands)}"
        command = commands[0]
        command_id = command["id"]
        print(f"   Comando ID: {command_id}")
        print(f"   Entidad: {command['entity_type']}:{command['entity_name']}")
        assert command["entity_type"] == "service"
        assert command["entity_name"] == "nginx"
        
        # 10. Simular agente: ejecutar restart (mock: success)
        print("\n10. Simulando agente ejecutando restart (systemctl restart nginx)...")
        result = await report_command_result(
            client, api_key, command_id, 
            status="success", exit_code=0, output_tail="nginx restarted successfully"
        )
        print(f"   OK: Resultado reportado: {result.get('status')}")
        
        # 11. Verificar que servicio vuelve a RUNNING (via ingesta agente)
        print("\n11. Verificando servicio recuperado (simulando agente reportando RUNNING)...")
        await update_service_status_via_ingest(client, api_key, server_id, "nginx", "running")
        await asyncio.sleep(1)
        service = await get_service_status(client, token, service_id)
        print(f"   Estado final: {service.get('last_status', 'unknown')}")
        assert service.get("last_status") == "running", f"Esperaba running, got {service.get('last_status')}"
        
        # 12. Verificar que no hay comandos pendientes (ya procesado)
        print("\n12. Verificando no hay comandos pendientes...")
        commands = await list_pending_commands(client, api_key, server_id)
        print(f"   Comandos pendientes: {len(commands)}")
        assert len(commands) == 0
        
        print("\n[OK] E2E AUTO-RESTART TEST PASSED")
        print("\nResumen del flujo validado:")
        print("   1. Usuario + API key creados")
        print("   2. Server registrado (agente)")
        print("   3. Servicio nginx con auto_restart=true")
        print("   4. Servicio cae a STOPPED")
        print("   5. Regla de alerta SERVICE creada")
        print("   6. Worker evalua -> encola auto-restart")
        print("   7. Agente poll /commands -> obtiene comando")
        print("   8. Agente ejecuta restart (mock success)")
        print("   9. Agente reporta resultado SUCCESS")
        print("   10. Agente reporta servicio RUNNING via ingesta")
        print("   11. Servicio recuperado, sin comandos pendientes")
        return True


if __name__ == "__main__":
    from datetime import datetime
    API_URL = "http://localhost:8000"
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nE2E TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)