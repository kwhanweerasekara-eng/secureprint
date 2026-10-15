from apps.api.security.auth import decode_access_token, hash_password, verify_password


def test_password_is_hashed_not_plaintext():
    h = hash_password("MySecretPass1!")
    assert h != "MySecretPass1!"
    assert h.startswith("$argon2")


def test_password_verification_roundtrip():
    h = hash_password("MySecretPass1!")
    assert verify_password("MySecretPass1!", h) is True
    assert verify_password("WrongPassword", h) is False


def test_login_success_sets_httponly_cookie(client):
    resp = client.post("/api/v1/auth/login", json={"username": "staff", "password": "staff123"})
    assert resp.status_code == 200
    assert "secureprint_session" in resp.cookies
    body = resp.json()
    assert body["username"] == "staff"
    assert body["role"] == "USER"


def test_login_failure_wrong_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "staff", "password": "wrong"})
    assert resp.status_code == 401


def test_unauthenticated_request_rejected(client):
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 401


def test_staff_cannot_access_admin_routes(staff_client):
    resp = staff_client.get("/api/v1/rules")
    assert resp.status_code == 403


def test_admin_can_access_admin_routes(admin_client):
    resp = admin_client.get("/api/v1/rules")
    assert resp.status_code == 200


def test_jwt_roundtrip_contains_role(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.cookies["secureprint_session"]
    payload = decode_access_token(token)
    assert payload["role"] == "ADMIN"
