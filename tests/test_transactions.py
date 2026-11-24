import uuid
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.test_app import build_auth_app
from backend.database import init_db, get_db
from backend.bootstrap_admin import bootstrap_admin


RUN_ID = uuid.uuid4().hex[:8]
CUSTOMER_A = f"a.{RUN_ID}@example.com"
CUSTOMER_B = f"b.{RUN_ID}@example.com"
ADMIN_EMAIL = f"admin.{RUN_ID}@example.com"
PASSWORD = "StrongPass@2026!"


class MockAsyncClient:
    response_mode = "normal"
    response_barrier = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        if self.response_barrier is not None:
            self.response_barrier.wait(timeout=10)
        if self.response_mode == "unavailable":
            raise httpx.ConnectError("test scoring service unavailable", request=httpx.Request("POST", url))
        if self.response_mode == "invalid":
            return MockResponse("APPROVE", json["transaction_id"], invalid=True)
        amount = json["features"]["amount"]
        decision = "APPROVE" if amount < 100 else "DECLINE"
        return MockResponse(decision, json["transaction_id"])


class MockResponse:
    def __init__(self, decision, transaction_id, invalid=False):
        self._body = {
            "transaction_id": transaction_id,
            "fraud_probability": 0.05 if decision == "APPROVE" else 0.95,
            "raw_fraud_probability": 2.0 if invalid else (0.04 if decision == "APPROVE" else 0.90),
            "calibrated_fraud_probability": 0.05 if decision == "APPROVE" else 0.95,
            "scoring_latency_ms": 1.5,
            "decision": decision,
            "model_version": "test-model",
            "reasons": [] if decision == "APPROVE" else ["Suspicious transfer"],
        }

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture(scope="module")
def app_client():
    original_async_client = httpx.AsyncClient
    httpx.AsyncClient = MockAsyncClient
    init_db()
    bootstrap_admin(ADMIN_EMAIL, "Test Admin", PASSWORD)
    app = build_auth_app()
    with TestClient(app) as client:
        yield client
    httpx.AsyncClient = original_async_client


def register(client, email):
    return client.post("/api/auth/register/customer", json={
        "full_name": f"Customer {email}",
        "email": email,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    })


def login(client, email, role="CUSTOMER"):
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": PASSWORD,
        "portal_type": role,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_customer_accounts_and_recipient_listing(app_client):
    assert register(app_client, CUSTOMER_A).status_code == 201
    assert register(app_client, CUSTOMER_B).status_code == 201
    token_a = login(app_client, CUSTOMER_A)
    account = app_client.get("/api/customer/account", headers=auth(token_a))
    assert account.status_code == 200
    assert account.json()["balance_cents"] == 1000000
    assert account.json()["simulated"] is True
    recipients = app_client.get("/api/customer/recipients", headers=auth(token_a))
    assert recipients.status_code == 200
    assert any(item["email"] == CUSTOMER_B for item in recipients.json()["recipients"])


def test_approved_transfer_updates_both_balances_and_is_idempotent(app_client):
    token_a = login(app_client, CUSTOMER_A)
    token_b = login(app_client, CUSTOMER_B)
    recipient_list = app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
    recipient = next(item for item in recipient_list if item["email"] == CUSTOMER_B)
    body = {
        "recipient": recipient["id"],
        "amount": 50,
        "description": "Test transfer",
        "idempotency_key": f"idem-{RUN_ID}",
    }
    first = app_client.post("/api/customer/transfers", json=body, headers=auth(token_a))
    assert first.status_code == 200
    assert first.json()["decision"] == "APPROVE"
    assert first.json()["status"] == "COMPLETED"

    account_a = app_client.get("/api/customer/account", headers=auth(token_a)).json()
    account_b = app_client.get("/api/customer/account", headers=auth(token_b)).json()
    assert account_a["balance_cents"] == 995000
    assert account_b["balance_cents"] == 1005000

    second = app_client.post("/api/customer/transfers", json=body, headers=auth(token_a))
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    account_a_again = app_client.get("/api/customer/account", headers=auth(token_a)).json()
    assert account_a_again["balance_cents"] == 995000
    with get_db() as conn:
        entries = conn.execute(
            "SELECT entry_type, amount_cents FROM ledger_entries WHERE transaction_id = ?",
            (first.json()["id"],),
        ).fetchall()
    assert {(row["entry_type"], row["amount_cents"]) for row in entries} == {
        ("DEBIT", 5000), ("CREDIT", 5000),
    }

    mismatched_retry = app_client.post("/api/customer/transfers", json={
        **body, "amount": 51,
    }, headers=auth(token_a))
    assert mismatched_retry.status_code == 409


def test_decline_does_not_move_funds_and_history_is_scoped(app_client):
    token_a = login(app_client, CUSTOMER_A)
    token_b = login(app_client, CUSTOMER_B)
    recipient_list = app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
    recipient = next(item for item in recipient_list if item["email"] == CUSTOMER_B)
    before = app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"]
    response = app_client.post("/api/customer/transfers", json={
        "recipient": recipient["id"],
        "amount": 200,
        "idempotency_key": f"decline-{RUN_ID}",
    }, headers=auth(token_a))
    assert response.status_code == 200
    assert response.json()["decision"] == "DECLINE"
    assert response.json()["status"] == "DECLINED"
    after = app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"]
    assert after == before

    history_b = app_client.get("/api/customer/transfers", headers=auth(token_b))
    assert history_b.status_code == 200
    with get_db() as conn:
        user_b = conn.execute("SELECT id FROM users WHERE email = ?", (CUSTOMER_B,)).fetchone()
    assert all(
        item["sender_id"] == user_b["id"] or item["recipient_id"] == user_b["id"]
        for item in history_b.json()["transactions"]
    )


def test_overdraft_is_rejected(app_client):
    token_a = login(app_client, CUSTOMER_A)
    recipient_list = app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
    recipient = next(item for item in recipient_list if item["email"] == CUSTOMER_B)
    response = app_client.post("/api/customer/transfers", json={
        "recipient": recipient["id"],
        "amount": 999999,
        "idempotency_key": f"overdraft-{RUN_ID}",
    }, headers=auth(token_a))
    assert response.status_code in (422, 503)


def test_admin_monitoring_is_role_protected(app_client):
    token_customer = login(app_client, CUSTOMER_A)
    denied = app_client.get("/api/admin/transactions", headers=auth(token_customer))
    assert denied.status_code == 403
    token_admin = login(app_client, ADMIN_EMAIL, "ADMIN")
    allowed = app_client.get("/api/admin/transactions", headers=auth(token_admin))
    assert allowed.status_code == 200


def test_scoring_failure_is_retryable_without_moving_funds(app_client, monkeypatch):
    token_a = login(app_client, CUSTOMER_A)
    recipient = next(
        item for item in app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
        if item["email"] == CUSTOMER_B
    )
    body = {
        "recipient": recipient["id"],
        "amount": 25,
        "idempotency_key": f"retry-{RUN_ID}",
    }
    before = app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"]
    monkeypatch.setattr(MockAsyncClient, "response_mode", "unavailable")
    failed = app_client.post("/api/customer/transfers", json=body, headers=auth(token_a))
    assert failed.status_code == 503
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM transactions WHERE sender_id = (SELECT id FROM users WHERE email = ?) "
            "AND idempotency_key = ?",
            (CUSTOMER_A, body["idempotency_key"]),
        ).fetchone()
    assert row["status"] == "RETRYABLE"
    assert app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"] == before

    monkeypatch.setattr(MockAsyncClient, "response_mode", "normal")
    retried = app_client.post("/api/customer/transfers", json=body, headers=auth(token_a))
    assert retried.status_code == 200
    assert retried.json()["status"] == "COMPLETED"


def test_invalid_ml_response_never_executes_transfer(app_client, monkeypatch):
    token_a = login(app_client, CUSTOMER_A)
    recipient = next(
        item for item in app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
        if item["email"] == CUSTOMER_B
    )
    before = app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"]
    monkeypatch.setattr(MockAsyncClient, "response_mode", "invalid")
    response = app_client.post("/api/customer/transfers", json={
        "recipient": recipient["id"],
        "amount": 25,
        "idempotency_key": f"invalid-{RUN_ID}",
    }, headers=auth(token_a))
    assert response.status_code == 502
    assert app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"] == before
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM transactions WHERE idempotency_key = ?",
            (f"invalid-{RUN_ID}",),
        ).fetchone()
    assert row["status"] == "INVALID_ML_RESPONSE"


def test_simultaneous_approved_transfers_cannot_overdraw(app_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    email_a = f"concurrent-a.{RUN_ID}@example.com"
    email_b = f"concurrent-b.{RUN_ID}@example.com"
    assert register(app_client, email_a).status_code == 201
    assert register(app_client, email_b).status_code == 201
    token_a = login(app_client, email_a)
    token_b = login(app_client, email_b)
    recipient = next(
        item for item in app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
        if item["email"] == email_b
    )
    with get_db() as conn:
        sender_id = conn.execute("SELECT id FROM users WHERE email = ?", (email_a,)).fetchone()["id"]
        conn.execute("UPDATE accounts SET balance_cents = 10000 WHERE user_id = ?", (sender_id,))
    monkeypatch.setattr(MockAsyncClient, "response_barrier", Barrier(2))

    def transfer(key):
        with TestClient(app_client.app) as concurrent_client:
            return concurrent_client.post("/api/customer/transfers", json={
                "recipient": recipient["id"],
                "amount": 70,
                "idempotency_key": key,
            }, headers=auth(token_a))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(transfer, (f"parallel-a-{RUN_ID}", f"parallel-b-{RUN_ID}")))
    assert all(response.status_code == 200 for response in responses), [
        (response.status_code, response.text) for response in responses
    ]
    assert sorted(response.json()["status"] for response in responses) == [
        "COMPLETED", "FAILED_INSUFFICIENT_FUNDS",
    ]
    account_a = app_client.get("/api/customer/account", headers=auth(token_a)).json()
    account_b = app_client.get("/api/customer/account", headers=auth(token_b)).json()
    assert account_a["balance_cents"] == 3000
    assert account_b["balance_cents"] == 1007000


def test_live_features_use_prior_history_and_match_model_order():
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from backend.customer_routes import _transaction_features
    from features import FEATURE_COLUMNS

    conn = sqlite3.connect(":memory:")
    conn.row_factory = __import__("sqlite3").Row
    conn.execute("""
        CREATE TABLE transactions (
            id TEXT, sender_id TEXT, recipient_id TEXT, amount_cents INTEGER, created_at TEXT
        )
    """)
    now = datetime.now(timezone.utc)
    previous = (now - timedelta(hours=2)).isoformat()
    conn.execute(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
        ("prior", "sender", "recipient", 5000, previous),
    )
    conn.execute(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
        ("current", "sender", "recipient", 2500, now.isoformat()),
    )
    features = _transaction_features(
        conn.cursor(), "sender", "recipient", "current", 2500, 1000000, 0, now.isoformat(),
    )
    assert list(features) == FEATURE_COLUMNS
    assert len(features) == 22
    assert features["amount"] == 25
    assert features["amount_to_balance"] == 25 / 10001
    assert features["orig_cnt_1h"] == 0
    assert features["orig_cnt_24h"] == 1
    assert features["orig_cnt_7d"] == 1
    assert features["orig_sum_24h"] == 50
    assert features["orig_prior_cnt"] == 1
    assert features["orig_hrs_since_last"] == pytest.approx(2, abs=0.01)
    assert features["orig_amount_vs_mean"] == 0.5
    no_history = _transaction_features(
        conn.cursor(), "new-sender", "new-recipient", "new-current",
        2500, 1000000, 0, now.isoformat(),
    )
    assert no_history["orig_cnt_24h"] == 0
    assert no_history["orig_hrs_since_last"] is None
    assert no_history["orig_amount_vs_mean"] is None
    assert no_history["dest_hrs_since_last"] is None
    assert no_history["dest_amount_vs_mean"] is None


def test_ledger_failure_rolls_back_both_balances(app_client):
    import sqlite3

    token_a = login(app_client, CUSTOMER_A)
    token_b = login(app_client, CUSTOMER_B)
    recipient = next(
        item for item in app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
        if item["email"] == CUSTOMER_B
    )
    before_a = app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"]
    before_b = app_client.get("/api/customer/account", headers=auth(token_b)).json()["balance_cents"]
    trigger = f"fail_ledger_insert_{RUN_ID}"
    with get_db() as conn:
        conn.execute(f"""
            CREATE TRIGGER {trigger} BEFORE INSERT ON ledger_entries
            BEGIN SELECT RAISE(ABORT, 'injected ledger failure'); END
        """)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            app_client.post("/api/customer/transfers", json={
                "recipient": recipient["id"],
                "amount": 25,
                "idempotency_key": f"rollback-{RUN_ID}",
            }, headers=auth(token_a))
    finally:
        with get_db() as conn:
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")

    assert app_client.get("/api/customer/account", headers=auth(token_a)).json()["balance_cents"] == before_a
    assert app_client.get("/api/customer/account", headers=auth(token_b)).json()["balance_cents"] == before_b
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM transactions WHERE idempotency_key = ?",
            (f"rollback-{RUN_ID}",),
        ).fetchone()
        entries = conn.execute(
            "SELECT COUNT(*) FROM ledger_entries WHERE transaction_id = "
            "(SELECT id FROM transactions WHERE idempotency_key = ?)",
            (f"rollback-{RUN_ID}",),
        ).fetchone()[0]
    assert row["status"] == "SCORING"
    assert entries == 0


def test_transfer_rejects_frontend_scores_and_fractional_cents(app_client):
    token_a = login(app_client, CUSTOMER_A)
    recipients = app_client.get("/api/customer/recipients", headers=auth(token_a)).json()["recipients"]
    recipient = next(item for item in recipients if item["email"] == CUSTOMER_B)
    base = {"recipient": recipient["id"], "idempotency_key": f"invalid-input-{RUN_ID}"}
    extra_score = app_client.post("/api/customer/transfers", json={
        **base, "amount": 10, "fraud_probability": 0, "decision": "APPROVE",
    }, headers=auth(token_a))
    fractional_cent = app_client.post("/api/customer/transfers", json={
        **base, "amount": 10.001,
    }, headers=auth(token_a))
    assert extra_score.status_code == 422
    assert fractional_cent.status_code == 422
