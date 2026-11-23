from fastapi import APIRouter, Depends
from backend.middleware import require_role
from backend.database import get_db

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])

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
