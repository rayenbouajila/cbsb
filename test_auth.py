from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_register_client():
    response = client.post("/auth/register", json={
        "email": "nouveau@test.fr",
        "full_name": "Test User",
        "company_name": "Test SARL"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_login_admin():
    response = client.post("/auth/login", json={
        "email": "admin@comptaflow.com",
        "password": "rayen123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password():
    response = client.post("/auth/login", json={
        "email": "admin@comptaflow.com",
        "password": "mauvais_mot_de_passe"
    })
    assert response.status_code == 400
