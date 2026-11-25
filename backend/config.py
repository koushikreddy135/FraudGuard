import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List

# Automatically load environment configuration from the project root.
# Keep support for the conventional .env name while accepting api.env.
project_root = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=project_root / ".env")
load_dotenv(dotenv_path=project_root / "api.env")

class Settings(BaseModel):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev_fraudguard_super_secret_jwt_key_at_least_32_bytes_long!")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./fraudguard.db")
    
    # SMTP
    SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "False").lower() in ("true", "1", "t")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "security@fraudguard.local")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "FraudGuard Security")
    
    # Security Policies
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
    OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    MAX_OTP_ATTEMPTS: int = int(os.getenv("MAX_OTP_ATTEMPTS", "5"))

    # Google OAuth 2.0 / OpenID Connect
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/oauth/google/callback")

    ML_SERVICE_URL: str = os.getenv(
    "ML_SERVICE_URL",
    "http://127.0.0.1:8001"
)
    ML_SERVICE_TIMEOUT_SECONDS: float = float(os.getenv("ML_SERVICE_TIMEOUT_SECONDS", "5"))
    ML_API_KEY: str = os.getenv("ML_API_KEY", "")

    # Trusted CORS Frontend Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]


settings = Settings()
