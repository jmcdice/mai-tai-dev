"""Registration, login, and token refresh."""

from tests.conftest import auth_headers, login_user, register_user


def test_register_provisions_user_workspace_and_key(client):
    reg = register_user(client, email="first@example.com")

    assert reg["user"]["email"] == "first@example.com"
    assert reg["workspace"]["name"] == "My Workspace"
    assert reg["workspace"]["settings"] == {"dude_mode": False}
    # User-level API key, raw value only returned here
    assert reg["api_key"]["key"].startswith("mt_")


def test_first_user_is_admin_second_is_not(client):
    first = register_user(client, email="first@example.com")
    second = register_user(client, email="second@example.com")

    assert first["user"]["is_admin"] is True
    assert second["user"]["is_admin"] is False


def test_register_duplicate_email_rejected(client):
    register_user(client, email="dup@example.com")
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "test-password-123", "name": "Dup"},
    )
    assert resp.status_code == 400


def test_login_and_me(client):
    register_user(client, email="login@example.com")
    tokens = login_user(client, email="login@example.com")

    resp = client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["email"] == "login@example.com"


def test_login_wrong_password_rejected(client):
    register_user(client, email="wrong@example.com")
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "wrong@example.com", "password": "not-the-password"},
    )
    assert resp.status_code == 401


def test_refresh_flow(client):
    register_user(client, email="refresh@example.com")
    tokens = login_user(client, email="refresh@example.com")

    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]

    # An access token must not be usable as a refresh token
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert resp.status_code == 401
