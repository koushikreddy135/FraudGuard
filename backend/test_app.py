"""
Standalone auth test client — builds an auth-only FastAPI app without loading the ML model.
This allows auth/RBAC tests to run independently of LightGBM model availability.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth_routes import router as auth_router
from backend.customer_routes import router as customer_router
from backend.admin_routes import router as admin_router
from backend.database import init_db
from backend.config import settings

def build_auth_app() -> FastAPI:
    """Build and return a minimal auth-only FastAPI application for testing."""
    app = FastAPI(title="FraudGuard Auth Test App")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    )
    app.include_router(auth_router)
    app.include_router(customer_router)
    app.include_router(admin_router)
    init_db()
    return app
