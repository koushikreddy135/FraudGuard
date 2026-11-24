from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

from backend.middleware import require_role
from backend.database import get_db

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class ReviewActionRequest(BaseModel):
    transaction_id: str
    action: str  # 'APPROVE' or 'REJECT'
    notes: str = ""

@router.post("/transactions/review")
async def review_transaction(req: ReviewActionRequest, user: dict = Depends(require_role(["ADMIN"]))):
    """
    Allows Admin to manually approve or reject a transaction under REVIEW or PENDING_REVIEW.
    If approved, executes atomic debit/credit fund transfer.
    """
    action = req.action.upper()
    if action not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="Action must be APPROVE or REJECT.")

    now = _utc_now()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        tx = cursor.execute("SELECT * FROM transactions WHERE id = ?", (req.transaction_id,)).fetchone()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found.")

        if tx["status"] not in ("PENDING_REVIEW", "REQUIRES_VERIFICATION"):
            raise HTTPException(status_code=400, detail=f"Cannot review transaction with status {tx['status']}.")

        amount_cents = tx["amount_cents"]
        sender_id = tx["sender_id"]
        recipient_id = tx["recipient_id"]

        sender_account = cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (sender_id,)).fetchone()
        recipient_account = cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (recipient_id,)).fetchone()

        if action == "APPROVE":
            if not sender_account or not recipient_account:
                raise HTTPException(status_code=400, detail="Sender or recipient account not found.")
            if sender_account["balance_cents"] < amount_cents:
                cursor.execute("""
                    UPDATE transactions SET status = 'FAILED_INSUFFICIENT_FUNDS', updated_at = ? WHERE id = ?
                """, (now, tx["id"]))
                raise HTTPException(status_code=400, detail="Insufficient sender balance to approve.")

            sender_before = sender_account["balance_cents"]
            sender_after = sender_before - amount_cents
            recipient_before = recipient_account["balance_cents"]
            recipient_after = recipient_before + amount_cents

            cursor.execute("""
                UPDATE accounts SET balance_cents = ?, updated_at = ? WHERE id = ?
            """, (sender_after, now, sender_account["id"]))
            cursor.execute("""
                UPDATE accounts SET balance_cents = ?, updated_at = ? WHERE id = ?
            """, (recipient_after, now, recipient_account["id"]))

            cursor.executemany("""
                INSERT INTO ledger_entries (
                    id, transaction_id, account_id, entry_type, amount_cents,
                    balance_before_cents, balance_after_cents, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (f"led_{uuid.uuid4().hex}", tx["id"], sender_account["id"], "DEBIT",
                 amount_cents, sender_before, sender_after, now),
                (f"led_{uuid.uuid4().hex}", tx["id"], recipient_account["id"], "CREDIT",
                 amount_cents, recipient_before, recipient_after, now),
            ])

            cursor.execute("""
                UPDATE transactions SET
                    status = 'COMPLETED',
                    decision = 'MANUALLY_APPROVED',
                    sender_balance_after_cents = ?,
                    recipient_balance_after_cents = ?,
                    updated_at = ?
                WHERE id = ?
            """, (sender_after, recipient_after, now, tx["id"]))

            cursor.execute("""
                INSERT INTO audit_logs (id, user_id, action, details, created_at)
                VALUES (?, ?, 'ADMIN_OVERRIDE_APPROVE', ?, ?)
            """, (f"aud_{uuid.uuid4().hex}", user["id"], f"Admin approved {tx['id']} for ${amount_cents/100:.2f}. Notes: {req.notes}", now))

            return {"success": True, "status": "COMPLETED", "message": "Transaction manually approved and settled."}

        else: # REJECT
            cursor.execute("""
                UPDATE transactions SET
                    status = 'DECLINED',
                    decision = 'MANUALLY_DECLINED',
                    updated_at = ?
                WHERE id = ?
            """, (now, tx["id"]))

            cursor.execute("""
                INSERT INTO audit_logs (id, user_id, action, details, created_at)
                VALUES (?, ?, 'ADMIN_OVERRIDE_REJECT', ?, ?)
            """, (f"aud_{uuid.uuid4().hex}", user["id"], f"Admin rejected {tx['id']} for ${amount_cents/100:.2f}. Notes: {req.notes}", now))

            return {"success": True, "status": "DECLINED", "message": "Transaction manually declined by admin."}

@router.get("/transactions")
async def get_all_transactions(user: dict = Depends(require_role(["ADMIN"]))):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT t.*,
                   su.full_name AS sender_name,
                   su.email AS sender_email,
                   ru.full_name AS recipient_name,
                   ru.email AS recipient_email
            FROM transactions t
            JOIN users su ON su.id = t.sender_id
            JOIN users ru ON ru.id = t.recipient_id
            ORDER BY t.created_at DESC
            LIMIT 500
        """).fetchall()

    transactions = []
    for row in rows:
        import json
        transactions.append({
            "id": row["id"],
            "sender_id": row["sender_id"],
            "sender_name": row["sender_name"],
            "sender_email": row["sender_email"],
            "recipient_id": row["recipient_id"],
            "recipient_name": row["recipient_name"],
            "recipient_email": row["recipient_email"],
            "amount": row["amount_cents"] / 100,
            "fraud_probability": row["fraud_probability"],
            "calibrated_fraud_probability": row["fraud_probability"],
            "raw_fraud_probability": row["raw_fraud_probability"],
            "scoring_latency_ms": row["scoring_latency_ms"],
            "decision": row["decision"],
            "status": row["status"],
            "model_version": row["model_version"],
            "risk_reasons": json.loads(row["risk_reasons"]) if row["risk_reasons"] else [],
            "timestamp": row["created_at"],
        })
    return {"transactions": transactions}

@router.get("/dashboard")
async def get_admin_dashboard(user: dict = Depends(require_role(["ADMIN"]))):
    """
    Admin portal overview data.
    Protected strictly for users with ADMIN role.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'CUSTOMER'")
        customer_count = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN'")
        admin_count = cursor.fetchone()["count"]

        # Transaction volume & decisions summary
        cursor.execute("""
            SELECT
                COUNT(*) as total_txns,
                COALESCE(SUM(amount_cents), 0) as total_volume_cents,
                SUM(CASE WHEN decision = 'APPROVE' THEN 1 ELSE 0 END) as approved_count,
                SUM(CASE WHEN decision = 'REVIEW' OR decision = 'MANUALLY_APPROVED' OR decision = 'MANUALLY_DECLINED' THEN 1 ELSE 0 END) as review_count,
                SUM(CASE WHEN decision = 'STEP_UP' OR decision = 'VERIFIED_STEP_UP' THEN 1 ELSE 0 END) as stepup_count,
                SUM(CASE WHEN decision = 'DECLINE' THEN 1 ELSE 0 END) as declined_count,
                AVG(fraud_probability) as avg_fraud_prob,
                AVG(scoring_latency_ms) as avg_latency
            FROM transactions
        """)
        stats = cursor.fetchone()

        cursor.execute("""
            SELECT id, action, details, created_at, user_id
            FROM audit_logs
            ORDER BY created_at DESC LIMIT 15
        """)
        recent_logs = [dict(row) for row in cursor.fetchall()]

    return {
        "admin": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": "ADMIN",
            "access_level": "Full Security Operations"
        },
        "system_metrics": {
            "total_customers": customer_count,
            "total_admins": admin_count,
            "total_transactions": stats["total_txns"] or 0,
            "total_volume": (stats["total_volume_cents"] or 0) / 100,
            "approved_count": stats["approved_count"] or 0,
            "review_count": stats["review_count"] or 0,
            "stepup_count": stats["stepup_count"] or 0,
            "declined_count": stats["declined_count"] or 0,
            "avg_fraud_prob": round(float(stats["avg_fraud_prob"] or 0) * 100, 2),
            "avg_latency_ms": round(float(stats["avg_latency"] or 0), 2),
            "ml_engine_status": "Operational (LightGBM 22-Feature Engine)",
            "auth_guard": "Enforced"
        },
        "recent_audit_logs": recent_logs
    }


@router.get("/users")
async def get_all_users(user: dict = Depends(require_role(["ADMIN"]))):
    """
    Returns list of all users and their account balances.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.id, u.email, u.full_name, u.role, u.is_active, u.created_at,
                   a.id as account_id, a.balance_cents, a.currency
            FROM users u
            LEFT JOIN accounts a ON a.user_id = u.id
            ORDER BY u.created_at DESC
        """).fetchall()

    users = []
    for r in rows:
        users.append({
            "id": r["id"],
            "email": r["email"],
            "full_name": r["full_name"],
            "role": r["role"],
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
            "account_id": r["account_id"],
            "balance": (r["balance_cents"] or 0) / 100,
            "currency": r["currency"] or "USD",
        })
    return {"users": users}


@router.post("/users/{user_id}/toggle-status")
async def toggle_user_status(user_id: str, admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Activates or locks a customer account.
    """
    now = _utc_now()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        u = cursor.execute("SELECT id, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="User not found.")
        if u["id"] == admin["id"]:
            raise HTTPException(status_code=400, detail="Cannot disable your own administrator account.")

        new_status = 0 if u["is_active"] else 1
        cursor.execute("UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?", (new_status, now, user_id))
        status_text = "ENABLED" if new_status else "LOCKED"
        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'USER_STATUS_CHANGE', ?, ?)
        """, (f"aud_{uuid.uuid4().hex}", admin["id"], f"Admin changed user {user_id} status to {status_text}", now))

    return {"success": True, "user_id": user_id, "is_active": bool(new_status)}


@router.get("/model-ops")
async def get_model_ops(admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Returns live model version, training metrics, schema, and registry history.
    """
    from pathlib import Path
    import json
    model_dir = Path("artifacts")
    registry_dir = Path("sim_registry")

    version = (model_dir / "VERSION").read_text().strip() if (model_dir / "VERSION").exists() else "unknown"
    metrics = {}
    if (model_dir / "metrics.json").exists():
        metrics = json.loads((model_dir / "metrics.json").read_text())

    history = []
    if (registry_dir / "history.jsonl").exists():
        for line in (registry_dir / "history.jsonl").read_text().splitlines():
            if line.strip():
                try:
                    history.append(json.loads(line))
                except Exception:
                    pass

    return {
        "live_version": version,
        "metrics": metrics,
        "history": history[-10:],
    }


@router.post("/model-ops/rollback")
async def rollback_model(admin: dict = Depends(require_role(["ADMIN"]))):
    """
    Rolls back live model to previous version from registry.
    """
    import subprocess
    import sys
    now = _utc_now()
    try:
        proc = subprocess.run(
            [sys.executable, "retrain.py", "--rollback", "--registry", "sim_registry", "--current", "artifacts"],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Rollback failed: {proc.stderr or proc.stdout}")

        with get_db() as conn:
            conn.execute("""
                INSERT INTO audit_logs (id, user_id, action, details, created_at)
                VALUES (?, ?, 'MODEL_ROLLBACK', ?, ?)
            """, (f"aud_{uuid.uuid4().hex}", admin["id"], "Admin executed model version rollback", now))

        return {"success": True, "message": "Model rolled back successfully. Server reload active.", "output": proc.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
