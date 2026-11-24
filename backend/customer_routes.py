from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
import math
import time
from typing import Optional
import json
import uuid
import httpx

from backend.middleware import require_role
from backend.database import get_db
from backend.schemas import TransferRequest, StepUpVerifyRequest, ChangePasswordRequest
from backend.config import settings
from backend.security import hash_password, verify_password, hash_token, generate_secure_otp
from backend.email_service import send_otp_email
from features import FEATURE_COLUMNS

router = APIRouter(prefix="/api/customer", tags=["Customer Portal"])
logger = logging.getLogger(__name__)

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _centify(amount: float) -> int:
    try:
        decimal_amount = Decimal(str(amount))
        cents = decimal_amount * 100
        if not decimal_amount.is_finite() or cents != cents.to_integral_value():
            raise ValueError("Transfer amount must have no more than two decimal places.")
        return int(cents)
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Transfer amount must have no more than two decimal places.",
        )

def _recipient_row(cursor, recipient: str):
    cleaned = recipient.strip().lower()
    cursor.execute("""
        SELECT u.id, u.full_name, u.email, u.is_active, u.role,
               a.id AS account_id, a.balance_cents, a.currency
        FROM users u
        JOIN accounts a ON a.user_id = u.id
        WHERE u.role = 'CUSTOMER'
          AND u.is_active = 1
          AND (LOWER(u.email) = ? OR u.id = ? OR a.id = ?)
    """, (cleaned, recipient.strip(), recipient.strip()))
    return cursor.fetchone()

def _history_features(cursor, account_id: str, account_column: str, transaction_id: str,
                      now: str, amount: float, prefix: str) -> dict:
    if account_column not in ("sender_id", "recipient_id"):
        raise ValueError("Unsupported transaction history account column.")

    cursor.execute(f"""
        SELECT
            SUM(CASE WHEN julianday(created_at) >= julianday(?, '-1 hour') THEN 1 ELSE 0 END) AS cnt_1h,
            SUM(CASE WHEN julianday(created_at) >= julianday(?, '-24 hours') THEN 1 ELSE 0 END) AS cnt_24h,
            SUM(CASE WHEN julianday(created_at) >= julianday(?, '-168 hours') THEN 1 ELSE 0 END) AS cnt_7d,
            COALESCE(SUM(CASE WHEN julianday(created_at) >= julianday(?, '-24 hours')
                              THEN amount_cents ELSE 0 END), 0) AS sum_24h_cents,
            COUNT(*) AS prior_cnt,
            COALESCE(SUM(amount_cents), 0) AS prior_sum_cents,
            MAX(julianday(created_at)) AS last_at
        FROM transactions
        WHERE {account_column} = ?
          AND id != ?
          AND julianday(created_at) < julianday(?)
    """, (now, now, now, now, account_id, transaction_id, now))
    history = cursor.fetchone()
    hours_since_last = None
    amount_vs_mean = None
    if history["last_at"] is not None:
        hours_since_last = (cursor.execute(
            "SELECT julianday(?)", (now,)
        ).fetchone()[0] - history["last_at"]) * 24
    if history["prior_cnt"]:
        prior_mean = history["prior_sum_cents"] / history["prior_cnt"]
        amount_vs_mean = amount * 100 / prior_mean

    return {
        f"{prefix}_cnt_1h": int(history["cnt_1h"] or 0),
        f"{prefix}_cnt_24h": int(history["cnt_24h"] or 0),
        f"{prefix}_cnt_7d": int(history["cnt_7d"] or 0),
        f"{prefix}_sum_24h": history["sum_24h_cents"] / 100,
        f"{prefix}_prior_cnt": int(history["prior_cnt"]),
        f"{prefix}_hrs_since_last": hours_since_last,
        f"{prefix}_amount_vs_mean": amount_vs_mean,
    }

def _transaction_features(cursor, sender_id: str, recipient_id: str, transaction_id: str,
                          amount_cents: int, sender_balance_cents: int,
                          recipient_balance_cents: int, now: str) -> dict:
    amount = amount_cents / 100
    sender_balance = sender_balance_cents / 100
    sender_drain = amount >= sender_balance - 0.01
    features = {
        "amount": amount,
        "is_transfer": 1,
        "hour_of_day": datetime.fromisoformat(now).astimezone(timezone.utc).hour,
        "oldbalanceOrg": sender_balance,
        "amount_to_balance": amount / (sender_balance + 1.0),
        "drains_account": int(sender_drain),
        "oldbalanceDest": recipient_balance_cents / 100,
        "dest_was_empty": int(recipient_balance_cents == 0),
    }
    features.update(_history_features(cursor, sender_id, "sender_id", transaction_id, now, amount, "orig"))
    features.update(_history_features(cursor, recipient_id, "recipient_id", transaction_id, now, amount, "dest"))
    if set(features) != set(FEATURE_COLUMNS):
        raise RuntimeError("Live feature generation does not match the model feature schema.")
    ordered_features = {name: features[name] for name in FEATURE_COLUMNS}
    missing_count = sum(value is None for value in ordered_features.values())
    logger.debug(
        "Generated ML features transaction_id=%s feature_count=%d missing_count=%d",
        transaction_id, len(ordered_features), missing_count,
    )
    return ordered_features

@router.get("/account")
async def get_customer_account(user: dict = Depends(require_role(["CUSTOMER"]))):
    with get_db() as conn:
        account = conn.execute(
            "SELECT id, balance_cents, currency, updated_at FROM accounts WHERE user_id = ?",
            (user["id"],)
        ).fetchone()
    if not account:
        raise HTTPException(status_code=404, detail="Simulated account not found.")
    return {
        "id": account["id"],
        "balance": account["balance_cents"] / 100,
        "balance_cents": account["balance_cents"],
        "currency": account["currency"],
        "simulated": True,
        "updated_at": account["updated_at"],
    }

@router.get("/recipients")
async def get_recipients(user: dict = Depends(require_role(["CUSTOMER"]))):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.id, u.full_name, u.email, a.id AS account_id
            FROM users u
            JOIN accounts a ON a.user_id = u.id
            WHERE u.role = 'CUSTOMER' AND u.is_active = 1 AND u.id != ?
            ORDER BY u.full_name, u.email
        """, (user["id"],)).fetchall()
    return {"recipients": [dict(row) for row in rows]}

@router.post("/transfers")
async def create_transfer(req: TransferRequest, user: dict = Depends(require_role(["CUSTOMER"]))):
    amount_cents = _centify(req.amount)
    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="Transfer amount must be greater than zero.")

    idempotency_key = req.idempotency_key
    now = _utc_now()
    stale_before = (datetime.now(timezone.utc) - timedelta(
        seconds=max(30, settings.ML_SERVICE_TIMEOUT_SECONDS * 2)
    )).isoformat()
    transaction_id = f"txn_{uuid.uuid4().hex}"

    # Reserve and snapshot in a short write transaction. Never hold SQLite's write
    # lock while waiting for the external model service.
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        existing = cursor.execute(
            "SELECT * FROM transactions WHERE sender_id = ? AND idempotency_key = ?",
            (user["id"], idempotency_key),
        ).fetchone()
        if existing:
            if (
                existing["recipient_id"] != req.recipient
                and existing["recipient_id"] != (req.recipient.strip())
            ):
                recipient_for_key = _recipient_row(cursor, req.recipient)
                if not recipient_for_key or existing["recipient_id"] != recipient_for_key["id"]:
                    raise HTTPException(status_code=409, detail="Idempotency key was already used for another transfer.")
            if existing["amount_cents"] != amount_cents or existing["description"] != req.description:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for another transfer.")

            can_retry = existing["status"] == "RETRYABLE"
            is_stale = existing["status"] == "SCORING" and cursor.execute(
                "SELECT julianday(?) <= julianday(?)",
                (existing["updated_at"], stale_before),
            ).fetchone()[0]
            if not can_retry and not is_stale:
                return _serialize_transaction(existing)

            claimed = cursor.execute("""
                UPDATE transactions SET status = 'SCORING', updated_at = ?
                WHERE id = ? AND status = ?
            """, (now, existing["id"], existing["status"]))
            if claimed.rowcount != 1:
                current = cursor.execute(
                    "SELECT * FROM transactions WHERE id = ?", (existing["id"],)
                ).fetchone()
                return _serialize_transaction(current)
            transaction_id = existing["id"]
            recipient = _recipient_row(cursor, existing["recipient_id"])
            sender_account = cursor.execute(
                "SELECT * FROM accounts WHERE user_id = ?", (user["id"],)
            ).fetchone()
            if not sender_account or not recipient:
                raise HTTPException(status_code=404, detail="A transfer account is no longer available.")
            if sender_account["currency"] != recipient["currency"]:
                raise HTTPException(status_code=422, detail="Sender and recipient currencies do not match.")
            if amount_cents > sender_account["balance_cents"]:
                raise HTTPException(status_code=422, detail="Insufficient simulated funds.")
        else:
            sender_account = cursor.execute(
                "SELECT * FROM accounts WHERE user_id = ?", (user["id"],)
            ).fetchone()
            if not sender_account:
                raise HTTPException(status_code=404, detail="Your simulated account was not found.")
            if amount_cents > sender_account["balance_cents"]:
                raise HTTPException(status_code=422, detail="Insufficient simulated funds.")

            recipient = _recipient_row(cursor, req.recipient)
            if not recipient:
                raise HTTPException(status_code=404, detail="Recipient account was not found.")
            if recipient["id"] == user["id"]:
                raise HTTPException(status_code=422, detail="You cannot transfer funds to your own account.")
            if sender_account["currency"] != recipient["currency"]:
                raise HTTPException(status_code=422, detail="Sender and recipient currencies do not match.")

            cursor.execute("""
                INSERT INTO transactions (
                    id, idempotency_key, sender_id, recipient_id, amount_cents, description,
                    status, sender_balance_before_cents, sender_balance_after_cents,
                    recipient_balance_before_cents, recipient_balance_after_cents,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'SCORING', ?, ?, ?, ?, ?, ?)
            """, (
                transaction_id, idempotency_key, user["id"], recipient["id"], amount_cents,
                req.description, sender_account["balance_cents"], sender_account["balance_cents"],
                recipient["balance_cents"], recipient["balance_cents"], now, now,
            ))

        features = _transaction_features(
            cursor, user["id"], recipient["id"], transaction_id, amount_cents,
            sender_account["balance_cents"], recipient["balance_cents"], now,
        )
        cursor.execute("""
            UPDATE transactions SET ml_features = ?, updated_at = ?
            WHERE id = ? AND status = 'SCORING'
        """, (json.dumps(features, allow_nan=False), now, transaction_id))

    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ML_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.ML_SERVICE_URL.rstrip('/')}/score",
                json={
                    "transaction_id": transaction_id,
                    "amount": amount_cents / 100,
                    "features": features,
                },
            )
            response.raise_for_status()
            score = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        round_trip_ms = (time.perf_counter() - started_at) * 1000
        logger.warning(
            "ML scoring unavailable transaction_id=%s error_type=%s latency_ms=%.2f",
            transaction_id, type(exc).__name__, round_trip_ms,
        )
        with get_db() as conn:
            conn.execute("""
                UPDATE transactions
                SET status = 'RETRYABLE', risk_reasons = ?, scoring_latency_ms = ?, updated_at = ?
                WHERE id = ? AND status = 'SCORING'
            """, (
                json.dumps(["Fraud scoring service unavailable; retry with the same idempotency key"]),
                round_trip_ms, _utc_now(), transaction_id,
            ))
        raise HTTPException(
            status_code=503,
            detail="Fraud scoring is temporarily unavailable. No funds were moved; retry with the same idempotency key.",
        ) from exc

    round_trip_ms = (time.perf_counter() - started_at) * 1000
    valid_response = isinstance(score, dict)
    raw_probability = score.get("raw_fraud_probability") if valid_response else None
    calibrated_probability = score.get("calibrated_fraud_probability") if valid_response else None
    fraud_probability = score.get("fraud_probability") if valid_response else None
    decision = score.get("decision") if valid_response else None
    model_version = score.get("model_version") if valid_response else None
    reasons = score.get("reasons") if valid_response else None
    service_latency = score.get("scoring_latency_ms") if valid_response else None
    response_transaction_id = score.get("transaction_id") if valid_response else None
    valid_response = valid_response and all(
        type(value) in (int, float) and math.isfinite(float(value)) and 0 <= float(value) <= 1
        for value in (raw_probability, calibrated_probability, fraud_probability)
    )
    valid_response = valid_response and math.isclose(
        float(fraud_probability), float(calibrated_probability), rel_tol=0, abs_tol=1e-9,
    )
    valid_response = valid_response and decision in ("APPROVE", "STEP_UP", "REVIEW", "DECLINE")
    valid_response = valid_response and isinstance(model_version, str) and bool(model_version.strip())
    valid_response = valid_response and response_transaction_id == transaction_id
    valid_response = valid_response and isinstance(reasons, list) and all(
        isinstance(reason, str) for reason in reasons
    )
    valid_response = valid_response and type(service_latency) in (int, float) and (
        math.isfinite(float(service_latency)) and service_latency >= 0
    )
    if not valid_response:
        logger.error(
            "Invalid ML scoring response transaction_id=%s latency_ms=%.2f",
            transaction_id, round_trip_ms,
        )
        with get_db() as conn:
            conn.execute("""
                UPDATE transactions
                SET status = 'INVALID_ML_RESPONSE', risk_reasons = ?, scoring_latency_ms = ?, updated_at = ?
                WHERE id = ? AND status = 'SCORING'
            """, (
                json.dumps(["Fraud scoring returned an invalid response"]),
                round_trip_ms, _utc_now(), transaction_id,
            ))
        raise HTTPException(
            status_code=502,
            detail="Fraud scoring returned an invalid response. No funds were moved.",
        )

    status_by_decision = {
        "APPROVE": "COMPLETED",
        "STEP_UP": "REQUIRES_VERIFICATION",
        "REVIEW": "PENDING_REVIEW",
        "DECLINE": "DECLINED",
    }
    current_time = _utc_now()
    logger.info(
        "ML score received transaction_id=%s raw_probability=%.6f calibrated_probability=%.6f "
        "decision=%s model_version=%s service_latency_ms=%.2f round_trip_ms=%.2f",
        transaction_id, raw_probability, calibrated_probability, decision,
        model_version, service_latency, round_trip_ms,
    )
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        transaction = cursor.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not transaction or transaction["status"] != "SCORING":
            return _serialize_transaction(transaction) if transaction else None

        sender_account = cursor.execute("""
            SELECT a.* FROM accounts a
            JOIN users u ON u.id = a.user_id
            WHERE a.user_id = ? AND u.role = 'CUSTOMER' AND u.is_active = 1
        """, (user["id"],)).fetchone()
        recipient_account = cursor.execute("""
            SELECT a.* FROM accounts a
            JOIN users u ON u.id = a.user_id
            WHERE a.user_id = ? AND u.role = 'CUSTOMER' AND u.is_active = 1
        """, (transaction["recipient_id"],)).fetchone()
        if (
            not sender_account
            or not recipient_account
            or sender_account["currency"] != recipient_account["currency"]
        ):
            transaction_status = "FAILED_ACCOUNT_STATE"
            reasons = ["A transfer account became unavailable before finalization"]
            sender_before = transaction["sender_balance_before_cents"]
            recipient_before = transaction["recipient_balance_before_cents"]
            sender_after = sender_before
            recipient_after = recipient_before
        else:
            sender_before = sender_account["balance_cents"]
            recipient_before = recipient_account["balance_cents"]
            sender_after = sender_before
            recipient_after = recipient_before
            if decision == "APPROVE" and amount_cents > sender_before:
                transaction_status = "FAILED_INSUFFICIENT_FUNDS"
                reasons = ["Available balance changed before transfer finalization"]
            elif decision == "APPROVE":
                sender_after = sender_before - amount_cents
                recipient_after = recipient_before + amount_cents
                sender_update = cursor.execute("""
                    UPDATE accounts
                    SET balance_cents = balance_cents - ?, updated_at = ?
                    WHERE id = ? AND balance_cents >= ?
                """, (amount_cents, current_time, sender_account["id"], amount_cents))
                if sender_update.rowcount != 1:
                    raise RuntimeError("Sender balance changed during atomic transfer finalization.")
                recipient_update = cursor.execute("""
                    UPDATE accounts SET balance_cents = balance_cents + ?, updated_at = ?
                    WHERE id = ? AND balance_cents = ?
                """, (amount_cents, current_time, recipient_account["id"], recipient_before))
                if recipient_update.rowcount != 1:
                    raise RuntimeError("Recipient balance changed during atomic transfer finalization.")
                cursor.executemany("""
                    INSERT INTO ledger_entries (
                        id, transaction_id, account_id, entry_type, amount_cents,
                        balance_before_cents, balance_after_cents, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (f"led_{uuid.uuid4().hex}", transaction_id, sender_account["id"], "DEBIT",
                     amount_cents, sender_before, sender_after, current_time),
                    (f"led_{uuid.uuid4().hex}", transaction_id, recipient_account["id"], "CREDIT",
                     amount_cents, recipient_before, recipient_after, current_time),
                ])
                transaction_status = "COMPLETED"
            else:
                transaction_status = status_by_decision[decision]

        cursor.execute("""
            UPDATE transactions SET
                fraud_probability = ?, raw_fraud_probability = ?, scoring_latency_ms = ?,
                decision = ?, model_version = ?, status = ?, risk_reasons = ?, ml_features = ?,
                sender_balance_before_cents = ?, sender_balance_after_cents = ?,
                recipient_balance_before_cents = ?, recipient_balance_after_cents = ?,
                updated_at = ?
            WHERE id = ? AND status = 'SCORING'
        """, (
            float(calibrated_probability), float(raw_probability), float(service_latency),
            decision, model_version, transaction_status, json.dumps(reasons),
            json.dumps(features, allow_nan=False), sender_before, sender_after,
            recipient_before, recipient_after, current_time, transaction_id,
        ))
        if cursor.rowcount != 1:
            raise RuntimeError("Transaction state changed during finalization.")

        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'TRANSFER_PROCESSED', ?, ?)
        """, (
            f"aud_{uuid.uuid4().hex}",
            user["id"],
            f"{decision} transfer {transaction_id} for {amount_cents / 100:.2f}",
            current_time,
        ))

        # If decision is STEP_UP, generate a verification OTP and send to the customer's email
        if decision == "STEP_UP":
            stepup_otp = generate_secure_otp()
            stepup_hash = hash_token(stepup_otp)
            otp_expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
            cursor.execute("""
                INSERT INTO password_reset_otps (id, user_id, otp_hash, expires_at, attempts_left, is_used, created_at)
                VALUES (?, ?, ?, ?, 5, 0, ?)
            """, (f"otp_{uuid.uuid4().hex}", user["id"], stepup_hash, otp_expires, current_time))
            try:
                send_otp_email(user["email"], stepup_otp)
            except Exception as e:
                logger.error("Failed to deliver step-up verification email: %s", e)

        created = cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()

    return _serialize_transaction(created)

def _serialize_transaction(row) -> dict:
    risk_reasons = json.loads(row["risk_reasons"]) if row["risk_reasons"] else []
    return {
        "id": row["id"],
        "sender_id": row["sender_id"],
        "recipient_id": row["recipient_id"],
        "amount": row["amount_cents"] / 100,
        "amount_cents": row["amount_cents"],
        "description": row["description"],
        "fraud_probability": row["fraud_probability"],
        "calibrated_fraud_probability": row["fraud_probability"],
        "raw_fraud_probability": row["raw_fraud_probability"],
        "scoring_latency_ms": row["scoring_latency_ms"],
        "decision": row["decision"],
        "model_version": row["model_version"],
        "status": row["status"],
        "risk_reasons": risk_reasons,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

@router.get("/transfers")
async def list_customer_transfers(
    search: Optional[str] = None,
    decision: Optional[str] = None,
    user: dict = Depends(require_role(["CUSTOMER"])),
):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT t.*, su.full_name AS sender_name, su.email AS sender_email,
                   ru.full_name AS recipient_name, ru.email AS recipient_email
            FROM transactions t
            JOIN users su ON su.id = t.sender_id
            JOIN users ru ON ru.id = t.recipient_id
            WHERE t.sender_id = ? OR t.recipient_id = ?
            ORDER BY t.created_at DESC
        """, (user["id"], user["id"])).fetchall()

    result = []
    for row in rows:
        item = _serialize_transaction(row)
        item["sender_name"] = row["sender_name"]
        item["recipient_name"] = row["recipient_name"]
        if decision and (item["decision"] or "").upper() != decision.upper():
            continue
        haystack = f"{item['id']} {item['sender_name']} {item['recipient_name']} {item['description'] or ''}".lower()
        if search and search.lower() not in haystack:
            continue
        result.append(item)
    return {"transactions": result}

@router.post("/add-funds")
async def add_funds(req: dict, user: dict = Depends(require_role(["CUSTOMER"]))):
    """
    Simulated fund top-up. Adds the requested amount to the customer's account balance.
    No artificial deposit limits.
    """
    amount = req.get("amount")
    if amount is None or not isinstance(amount, (int, float)):
        raise HTTPException(status_code=422, detail="amount is required and must be a number.")

    amount_cents = _centify(float(amount))
    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="Amount must be greater than zero.")

    now = _utc_now()
    deposit_id = f"dep_{uuid.uuid4().hex}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        account = cursor.execute(
            "SELECT * FROM accounts WHERE user_id = ?", (user["id"],)
        ).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
        new_balance_cents = account["balance_cents"] + amount_cents
        cursor.execute(
            "UPDATE accounts SET balance_cents = ?, updated_at = ? WHERE id = ?",
            (new_balance_cents, now, account["id"])
        )
        cursor.execute(
            "INSERT INTO audit_logs (id, user_id, action, details, created_at) VALUES (?, ?, 'ADD_FUNDS', ?, ?)",
            (f"aud_{uuid.uuid4().hex}", user["id"], f"Deposited ${amount_cents / 100:.2f} simulated funds", now)
        )

    return {
        "success": True,
        "deposit_id": deposit_id,
        "amount": amount_cents / 100,
        "new_balance": new_balance_cents / 100,
        "currency": account["currency"],
    }


@router.get("/dashboard")
async def get_customer_dashboard(user: dict = Depends(require_role(["CUSTOMER"]))):
    """
    Customer portal overview data.
    Protected strictly for users with CUSTOMER role.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],))
        account = cursor.fetchone()
        cursor.execute("""
            SELECT id, recipient_id, amount_cents, decision, status, created_at
            FROM transactions
            WHERE sender_id = ? OR recipient_id = ?
            ORDER BY created_at DESC LIMIT 5
        """, (user["id"], user["id"]))
        recent = [dict(row) for row in cursor.fetchall()]

    return {
        "status": "active",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "account_tier": "Premier Secure",
            "security_status": "Shield Active - Protected by FraudGuard AI",
            "last_login": "Just now",
            "account": {
                "id": account["id"] if account else None,
                "balance": (account["balance_cents"] / 100) if account else 0,
                "balance_cents": account["balance_cents"] if account else 0,
                "currency": account["currency"] if account else "USD",
                "simulated": True
            }
        },
        "recent_activity": recent,
        "notifications": [
            {
                "id": "notif_1",
                "title": "Real-time AI Shield Active",
                "message": "Your account is actively protected against unauthorized outbound transfers and takeover attempts.",
                "type": "info"
            }
        ]
    }


@router.post("/transfers/verify-stepup")
async def verify_stepup_transfer(req: StepUpVerifyRequest, user: dict = Depends(require_role(["CUSTOMER"]))):
    """
    Submits OTP verification for a transaction held in REQUIRES_VERIFICATION (STEP_UP).
    If valid, finalizes atomic debit/credit transfer.
    """
    now = _utc_now()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        tx = cursor.execute(
            "SELECT * FROM transactions WHERE id = ? AND sender_id = ?",
            (req.transaction_id, user["id"])
        ).fetchone()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found.")
        if tx["status"] != "REQUIRES_VERIFICATION":
            raise HTTPException(status_code=400, detail=f"Transaction is in status {tx['status']}, not awaiting verification.")

        # Check latest active OTP for user
        otp_row = cursor.execute("""
            SELECT * FROM password_reset_otps
            WHERE user_id = ? AND is_used = 0 AND expires_at > ?
            ORDER BY created_at DESC LIMIT 1
        """, (user["id"], now)).fetchone()

        if not otp_row:
            raise HTTPException(status_code=400, detail="No active verification code found. Please initiate a new transfer.")

        if otp_row["attempts_left"] <= 0:
            raise HTTPException(status_code=400, detail="Maximum verification attempts exceeded.")

        if hash_token(req.otp) != otp_row["otp_hash"]:
            cursor.execute("""
                UPDATE password_reset_otps SET attempts_left = attempts_left - 1 WHERE id = ?
            """, (otp_row["id"],))
            raise HTTPException(status_code=400, detail=f"Invalid OTP code. {otp_row['attempts_left'] - 1} attempts remaining.")

        # Mark OTP used
        cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (otp_row["id"],))

        # Perform atomic transfer
        amount_cents = tx["amount_cents"]
        sender_account = cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()
        recipient_account = cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (tx["recipient_id"],)).fetchone()

        if not sender_account or not recipient_account:
            raise HTTPException(status_code=400, detail="Account unavailable.")
        if sender_account["balance_cents"] < amount_cents:
            cursor.execute("UPDATE transactions SET status = 'FAILED_INSUFFICIENT_FUNDS', updated_at = ? WHERE id = ?", (now, tx["id"]))
            raise HTTPException(status_code=400, detail="Insufficient account balance to settle transfer.")

        sender_before = sender_account["balance_cents"]
        sender_after = sender_before - amount_cents
        recipient_before = recipient_account["balance_cents"]
        recipient_after = recipient_before + amount_cents

        cursor.execute("UPDATE accounts SET balance_cents = ?, updated_at = ? WHERE id = ?", (sender_after, now, sender_account["id"]))
        cursor.execute("UPDATE accounts SET balance_cents = ?, updated_at = ? WHERE id = ?", (recipient_after, now, recipient_account["id"]))

        cursor.executemany("""
            INSERT INTO ledger_entries (id, transaction_id, account_id, entry_type, amount_cents, balance_before_cents, balance_after_cents, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (f"led_{uuid.uuid4().hex}", tx["id"], sender_account["id"], "DEBIT", amount_cents, sender_before, sender_after, now),
            (f"led_{uuid.uuid4().hex}", tx["id"], recipient_account["id"], "CREDIT", amount_cents, recipient_before, recipient_after, now)
        ])

        cursor.execute("""
            UPDATE transactions SET
                status = 'COMPLETED',
                decision = 'VERIFIED_STEP_UP',
                sender_balance_after_cents = ?,
                recipient_balance_after_cents = ?,
                updated_at = ?
            WHERE id = ?
        """, (sender_after, recipient_after, now, tx["id"]))

        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'STEP_UP_VERIFIED', ?, ?)
        """, (f"aud_{uuid.uuid4().hex}", user["id"], f"Customer verified step-up OTP for transfer {tx['id']}", now))

    return {"success": True, "status": "COMPLETED", "message": "Verification confirmed! Funds transferred successfully."}


@router.post("/security/change-password")
async def customer_change_password(req: ChangePasswordRequest, user: dict = Depends(require_role(["CUSTOMER"]))):
    """
    Allows authenticated customer to safely change their login password.
    """
    now = _utc_now()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        user_row = cursor.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")

        if not verify_password(req.current_password, user_row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")

        new_hash = hash_password(req.new_password)
        cursor.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (new_hash, now, user["id"]))

        # Revoke other active sessions for security
        cursor.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user["id"],))

        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'PASSWORD_CHANGED', ?, ?)
        """, (f"aud_{uuid.uuid4().hex}", user["id"], "Customer updated account security password", now))

    return {"success": True, "message": "Password changed successfully. Your account is secured."}
