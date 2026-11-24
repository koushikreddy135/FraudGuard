from fastapi import APIRouter, Depends
from backend.middleware import require_role
from backend.database import get_db

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])

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
        
        cursor.execute("""
            SELECT id, action, details, created_at, user_id
            FROM audit_logs
            ORDER BY created_at DESC LIMIT 10
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
            "ml_engine_status": "Operational (LightGBM 22-Feature Engine)",
            "auth_guard": "Enforced"
        },
        "recent_audit_logs": recent_logs
    }
