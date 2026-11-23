from fastapi import APIRouter, Depends
from backend.middleware import require_role
from backend.database import get_db

router = APIRouter(prefix="/api/customer", tags=["Customer Portal"])

@router.get("/dashboard")
async def get_customer_dashboard(user: dict = Depends(require_role(["CUSTOMER"]))):
    """
    Customer portal overview data.
    Protected strictly for users with CUSTOMER role.
    """
    return {
        "status": "active",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "account_tier": "Premier Secure",
            "security_status": "Shield Active - Protected by FraudGuard AI",
            "last_login": "Just now"
        },
        "notifications": [
            {
                "id": "notif_1",
                "title": "Real-time AI Shield Active",
                "message": "Your account is actively protected against unauthorized outbound transfers and takeover attempts.",
                "type": "info"
            }
        ]
    }
