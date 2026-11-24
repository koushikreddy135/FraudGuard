"""
Auth integration tests — uses a lightweight auth-only FastAPI app (no ML model load).
Covers: registration, login, role enforcement, RBAC, brute-force lockout, OTP flow.
"""
import hashlib
import uuid
import urllib.parse
import pytest
from fastapi.testclient import TestClient
from backend.test_app import build_auth_app
from backend.database import init_db, get_db
from backend.bootstrap_admin import bootstrap_admin

TEST_ADMIN_EMAIL = "secadmin@fraudguard.test"
TEST_ADMIN_NAME = "Security Lead"
TEST_ADMIN_PASS = "AdminPass@2026!"

# Use unique suffix per test run so persistent DB rows from prior runs never collide
_RUN_ID = uuid.uuid4().hex[:8]
CUSTOMER_EMAIL = f"alice.auth.{_RUN_ID}@example.com"

@pytest.fixture(scope="module")
def client():
    init_db()
    bootstrap_admin(TEST_ADMIN_EMAIL, TEST_ADMIN_NAME, TEST_ADMIN_PASS)
    app = build_auth_app()
    with TestClient(app) as c:
        yield c

# ───────────────────────────────────────────────
# REGISTRATION
# ───────────────────────────────────────────────

def test_customer_registration_success(client):
    res = client.post("/api/auth/register/customer", json={
        "full_name": "Alice Morgan",
        "email": CUSTOMER_EMAIL,
        "password": "SecurePassword@123",
        "confirm_password": "SecurePassword@123"
    })
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["email"] == CUSTOMER_EMAIL
    assert data["role"] == "CUSTOMER"
    assert "password" not in data
    assert "password_hash" not in data

def test_duplicate_registration_prevented(client):
    payload = {
        "full_name": "Alice Again",
        "email": CUSTOMER_EMAIL,
        "password": "SecurePassword@123",
        "confirm_password": "SecurePassword@123"
    }
    res = client.post("/api/auth/register/customer", json=payload)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]

def test_weak_password_rejected(client):
    res = client.post("/api/auth/register/customer", json={
        "full_name": "Weak User",
        "email": "weak.user@example.com",
        "password": "weak",
        "confirm_password": "weak"
    })
    assert res.status_code == 422

def test_password_mismatch_rejected(client):
    res = client.post("/api/auth/register/customer", json={
        "full_name": "Mismatch User",
        "email": "mismatch@example.com",
        "password": "StrongPass@2026!",
        "confirm_password": "DifferentPass@2026!"
    })
    assert res.status_code == 422

# ───────────────────────────────────────────────
# CUSTOMER LOGIN
# ───────────────────────────────────────────────

def test_customer_login_success(client):
    res = client.post("/api/auth/login", json={
        "email": CUSTOMER_EMAIL,
        "password": "SecurePassword@123",
        "portal_type": "CUSTOMER"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "CUSTOMER"

def test_invalid_credentials_rejected(client):
    res = client.post("/api/auth/login", json={
        "email": CUSTOMER_EMAIL,
        "password": "WrongPassword!",
        "portal_type": "CUSTOMER"
    })
    assert res.status_code == 401
    assert "Invalid" in res.json()["detail"]

def test_nonexistent_user_rejected(client):
    res = client.post("/api/auth/login", json={
        "email": "ghost@nobody.com",
        "password": "SomePass@123",
        "portal_type": "CUSTOMER"
    })
    assert res.status_code == 401
    # Must NOT leak whether email exists
    assert "Invalid" in res.json()["detail"]

# ───────────────────────────────────────────────
# ADMIN LOGIN
# ───────────────────────────────────────────────

def test_admin_login_success(client):
    res = client.post("/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": TEST_ADMIN_PASS,
        "portal_type": "ADMIN"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["user"]["role"] == "ADMIN"
    assert "access_token" in data

def test_admin_wrong_password(client):
    res = client.post("/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": "wrong",
        "portal_type": "ADMIN"
    })
    assert res.status_code == 401

# ───────────────────────────────────────────────
# CROSS-PORTAL ROLE ENFORCEMENT
# ───────────────────────────────────────────────

def test_customer_cannot_use_admin_portal(client):
    """Customer credentials must be REJECTED at admin portal."""
    res = client.post("/api/auth/login", json={
        "email": CUSTOMER_EMAIL,
        "password": "SecurePassword@123",
        "portal_type": "ADMIN"
    })
    assert res.status_code == 403
    assert "Administrative privileges" in res.json()["detail"]

def test_admin_cannot_use_customer_portal(client):
    """Admin credentials must be REJECTED at customer portal."""
    res = client.post("/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": TEST_ADMIN_PASS,
        "portal_type": "CUSTOMER"
    })
    assert res.status_code == 403
    assert "dedicated Admin Portal" in res.json()["detail"]

# ───────────────────────────────────────────────
# PROTECTED ROUTE ACCESS (RBAC)
# ───────────────────────────────────────────────

def _customer_token(client) -> str:
    r = client.post("/api/auth/login", json={
        "email": CUSTOMER_EMAIL,
        "password": "SecurePassword@123",
        "portal_type": "CUSTOMER"
    })
    return r.json()["access_token"]

def _admin_token(client) -> str:
    r = client.post("/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": TEST_ADMIN_PASS,
        "portal_type": "ADMIN"
    })
    return r.json()["access_token"]

def test_customer_can_access_own_dashboard(client):
    token = _customer_token(client)
    res = client.get("/api/customer/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == CUSTOMER_EMAIL

def test_customer_cannot_access_admin_dashboard(client):
    token = _customer_token(client)
    res = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

def test_admin_can_access_admin_dashboard(client):
    token = _admin_token(client)
    res = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["admin"]["role"] == "ADMIN"
    assert "system_metrics" in data
    assert "recent_audit_logs" in data

def test_admin_cannot_access_customer_dashboard(client):
    token = _admin_token(client)
    res = client.get("/api/customer/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403

def test_unauthenticated_access_rejected(client):
    # Use a fresh client with no cookies/headers to guarantee no token is present
    from fastapi.testclient import TestClient as _TC
    from backend.test_app import build_auth_app
    with _TC(build_auth_app()) as fresh:
        res = fresh.get("/api/customer/dashboard")
        assert res.status_code == 401
        res2 = fresh.get("/api/admin/dashboard")
        assert res2.status_code == 401

def test_invalid_token_rejected(client):
    res = client.get("/api/customer/dashboard", headers={"Authorization": "Bearer totallyinvalidtoken"})
    assert res.status_code == 401

# ───────────────────────────────────────────────
# BRUTE-FORCE LOCKOUT
# ───────────────────────────────────────────────

def test_brute_force_account_lockout(client):
    # Use a unique email each run so a locked account from a prior run doesn't interfere
    lockout_email = f"lockout.{_RUN_ID}@example.com"
    client.post("/api/auth/register/customer", json={
        "full_name": "Lock Target",
        "email": lockout_email,
        "password": "TargetPass@123",
        "confirm_password": "TargetPass@123"
    })

    # 4 wrong attempts should increment counter but not lock
    for _ in range(4):
        r = client.post("/api/auth/login", json={
            "email": lockout_email,
            "password": "WrongPassword!",
            "portal_type": "CUSTOMER"
        })
        assert r.status_code == 401

    # 5th wrong attempt → lockout (HTTP 429)
    r5 = client.post("/api/auth/login", json={
        "email": lockout_email,
        "password": "WrongPassword!",
        "portal_type": "CUSTOMER"
    })
    assert r5.status_code == 429
    assert "locked" in r5.json()["detail"]

# ───────────────────────────────────────────────
# /me ENDPOINT
# ───────────────────────────────────────────────

def test_me_returns_authenticated_user(client):
    token = _customer_token(client)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == CUSTOMER_EMAIL
    assert data["role"] == "CUSTOMER"

# ───────────────────────────────────────────────
# OTP PASSWORD RESET FLOW
# ───────────────────────────────────────────────

def test_forgot_password_otp_full_flow(client):
    # Use unique email per run to avoid cooldown conflicts from prior runs
    otp_email = f"otp.flow.{_RUN_ID}@example.com"
    client.post("/api/auth/register/customer", json={
        "full_name": "OTP Flow User",
        "email": otp_email,
        "password": "OldPassword@123",
        "confirm_password": "OldPassword@123"
    })

    # 1. Request OTP (generic message regardless of email existence)
    res = client.post("/api/auth/forgot-password", json={"email": otp_email})
    assert res.status_code == 200
    assert "verification code" in res.json()["message"].lower()

    # 2. Request OTP for non-existent email (must NOT fail or enumerate)
    res_ghost = client.post("/api/auth/forgot-password", json={"email": "ghost99@nowhere.com"})
    assert res_ghost.status_code == 200
    assert "verification code" in res_ghost.json()["message"].lower()

    # 3. Test wrong OTP is rejected with decrement
    bad_res = client.post("/api/auth/verify-otp", json={"email": otp_email, "otp": "000000"})
    assert bad_res.status_code == 400
    assert "Incorrect" in bad_res.json()["detail"]

    # 4. Inject a known hash into the DB to simulate a real OTP we "know"
    test_otp = "424242"
    test_hash = hashlib.sha256(test_otp.encode()).hexdigest()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT o.id FROM password_reset_otps o JOIN users u ON o.user_id = u.id "
            "WHERE u.email = ? AND o.is_used = 0 ORDER BY o.created_at DESC LIMIT 1",
            (otp_email,)
        )
        record = cursor.fetchone()
        assert record is not None, "No active OTP record found"
        cursor.execute("UPDATE password_reset_otps SET otp_hash = ?, attempts_left = 5 WHERE id = ?",
                       (test_hash, record["id"]))

    # 5. verify-otp with correct code returns valid: true
    verify_res = client.post("/api/auth/verify-otp", json={"email": otp_email, "otp": test_otp})
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True

    # 6. Reset password succeeds
    reset_res = client.post("/api/auth/reset-password", json={
        "email": otp_email,
        "otp": test_otp,
        "new_password": "NewSecurePass@2026!",
        "confirm_new_password": "NewSecurePass@2026!"
    })
    assert reset_res.status_code == 200
    assert "Password updated" in reset_res.json()["message"]

    # 7. OTP replay must be rejected (is_used = 1 now)
    replay_res = client.post("/api/auth/reset-password", json={
        "email": otp_email,
        "otp": test_otp,
        "new_password": "ReplayAttempt@2026!",
        "confirm_new_password": "ReplayAttempt@2026!"
    })
    assert replay_res.status_code == 400

    # 8. Old password no longer works
    old_login = client.post("/api/auth/login", json={
        "email": otp_email,
        "password": "OldPassword@123",
        "portal_type": "CUSTOMER"
    })
    assert old_login.status_code == 401

    # 9. New password works
    new_login = client.post("/api/auth/login", json={
        "email": otp_email,
        "password": "NewSecurePass@2026!",
        "portal_type": "CUSTOMER"
    })
    assert new_login.status_code == 200

# ───────────────────────────────────────────────
# LOGOUT
# ───────────────────────────────────────────────

def test_logout_clears_session(client):
    token = _customer_token(client)
    res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert "signed out" in res.json()["message"].lower()

# ───────────────────────────────────────────────
# ROLE TAMPERING & PRIVILEGE ESCALATION PREVENTION
# ───────────────────────────────────────────────

def test_registration_cannot_escalate_to_admin(client):
    """Passing role: ADMIN in public registration must be ignored/enforced as CUSTOMER."""
    tamper_email = f"tamper.{_RUN_ID}@example.com"
    res = client.post("/api/auth/register/customer", json={
        "full_name": "Tamper User",
        "email": tamper_email,
        "password": "SecurePassword@123",
        "confirm_password": "SecurePassword@123",
        "role": "ADMIN"  # Attempt privilege escalation
    })
    assert res.status_code == 201
    assert res.json()["role"] == "CUSTOMER"

    # Verify directly in SQLite
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE email = ?", (tamper_email,))
        row = cursor.fetchone()
        assert row["role"] == "CUSTOMER"

# ───────────────────────────────────────────────
# OTP ATTEMPT DURABILITY & REPLAY PREVENTION
# ───────────────────────────────────────────────

def test_otp_failed_attempts_decrement_durably(client):
    """Wrong OTP submissions must decrement attempts_left in SQLite even on HTTP 400 error."""
    test_email = f"otp.attempts.{_RUN_ID}@example.com"
    client.post("/api/auth/register/customer", json={
        "full_name": "Attempt User",
        "email": test_email,
        "password": "SecurePassword@123",
        "confirm_password": "SecurePassword@123"
    })
    client.post("/api/auth/forgot-password", json={"email": test_email})

    # Wrong attempt 1
    r1 = client.post("/api/auth/verify-otp", json={"email": test_email, "otp": "999999"})
    assert r1.status_code == 400

    # Verify attempt decrement persisted in database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT attempts_left FROM password_reset_otps o JOIN users u ON o.user_id = u.id "
            "WHERE u.email = ? AND o.is_used = 0 ORDER BY o.created_at DESC LIMIT 1",
            (test_email,)
        )
        record = cursor.fetchone()
        assert record is not None
        assert record["attempts_left"] == 4, f"Expected 4 attempts left, got {record['attempts_left']}"

# ───────────────────────────────────────────────
# GOOGLE OAUTH CSRF STATE VERIFICATION
# ───────────────────────────────────────────────

def test_google_oauth_csrf_protection(client):
    """Google OAuth callback without matching state cookie must be rejected."""
    # State provided in URL does not match any valid oauth_state cookie
    res = client.get("/api/auth/oauth/google/callback?code=fake_code&state=forged_state", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "oauth_error" in location
    assert "CSRF" in location or "state" in location


def test_google_oauth_state_is_scoped_per_attempt(client):
    first = client.get("/api/auth/oauth/google/url")
    assert first.status_code == 200
    first_url = first.json()["url"]
    assert first_url is not None
    first_state = urllib.parse.parse_qs(
        urllib.parse.urlparse(first_url).query
    )["state"][0]

    second = client.get("/api/auth/oauth/google/url")
    assert second.status_code == 200
    second_url = second.json()["url"]
    second_state = urllib.parse.parse_qs(
        urllib.parse.urlparse(second_url).query
    )["state"][0]
    assert first_state != second_state

    first_callback = client.get(
        "/api/auth/oauth/google/callback",
        params={"code": "fake-code", "state": first_state},
        follow_redirects=False,
    )
    assert first_callback.status_code == 307
    location = first_callback.headers["location"]
    assert "oauth_error" in location
    assert "Invalid or expired OAuth state" not in location


def test_google_oauth_redirect_uri_matches_request_origin(client):
    response = client.get(
        "/api/auth/oauth/google/url",
        headers={"Host": "localhost:8000"},
    )
    assert response.status_code == 200
    oauth_url = response.json()["url"]
    assert oauth_url is not None
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(oauth_url).query
    )
    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/oauth/google/callback"]

    loopback_response = client.get(
        "/api/auth/oauth/google/url",
        headers={"Host": "127.0.0.1:8000"},
    )
    loopback_url = loopback_response.json()["url"]
    loopback_query = urllib.parse.parse_qs(
        urllib.parse.urlparse(loopback_url).query
    )
    assert loopback_query["redirect_uri"] == [
        "http://127.0.0.1:8000/api/auth/oauth/google/callback"
    ]
