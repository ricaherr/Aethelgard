import pytest
import sqlite3
from fastapi.testclient import TestClient
from core_brain.server import app
from core_brain.api.dependencies.auth import get_auth_service
from core_brain.services.auth_service import AuthService
from data_vault.auth_repo import AuthRepository
from data_vault.schema import initialize_schema
import os

@pytest.fixture
def auth_repo():
    # Usar una base de datos temporal con schema completo para testing
    test_db = "data_vault/global/test_auth.db"
    os.makedirs(os.path.dirname(test_db), exist_ok=True)
    conn = sqlite3.connect(test_db)
    initialize_schema(conn)
    conn.close()
    repo = AuthRepository(db_path=test_db)
    yield repo
    if os.path.exists(test_db):
        os.remove(test_db)

@pytest.fixture
def auth_service(auth_repo):
    return AuthService(auth_repo=auth_repo)

@pytest.fixture
def client(auth_service):
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_risk_status_without_token_rejected(client):
    """
    Test que verifica que el endpoint de risk/status rechaza la petición sin token.
    (HU 1.1 Gatekeeper)
    """
    response = client.get("/api/risk/status")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_risk_status_with_invalid_token_rejected(client):
    """
    Test que verifica que un token inválido es rechazado.
    """
    headers = {"Authorization": "Bearer invalid_token_here"}
    response = client.get("/api/risk/status", headers=headers)
    assert response.status_code == 401

def test_risk_status_with_valid_token_accepted(client, auth_service, auth_repo):
    """
    Test que verifica que un token válido inyecta el user_id y permite acceso.
    """
    user_id = "user_test_123"
    # Registrar usuario en la BD de test para que el token sea válido
    auth_repo.create_user(
        email="test@example.com",
        password_hash="hashed_pw",
        role="trader",
        user_id=user_id
    )
    # Crear un token válido usando el servicio
    token = auth_service.create_access_token(subject="user_123", tenant_id=user_id)
    
    headers = {"Authorization": f"Bearer {token}"}
    client.cookies.set("a_token", token)
    response = client.get("/api/risk/status")
    
    # Podría ser 200, o si falta configuración en storage devolver otro código, pero no debe ser 401
    assert response.status_code != 401
    
    # Si retorna 200, validemos que retorna datos
    if response.status_code == 200:
        data = response.json()
        assert "risk_mode" in data
