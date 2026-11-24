from pydantic import BaseModel, ConfigDict, Field, field_validator
import re
from typing import Optional, List, Dict, Any

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_email_format(v: str) -> str:
    cleaned = v.strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email address format.")
    return cleaned

class CustomerRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_format(v)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match.")
        return v

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    password: str
    portal_type: str = Field("CUSTOMER", pattern="^(CUSTOMER|ADMIN)$")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_format(v)

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_format(v)

class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    otp: str = Field(..., min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_format(v)

class ResetPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_format(v)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("confirm_new_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    created_at: str

class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(..., min_length=2, max_length=160)
    amount: float = Field(..., gt=0, le=1000000)
    description: Optional[str] = Field(default=None, max_length=240)
    idempotency_key: str = Field(..., min_length=8, max_length=128)

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Recipient is required.")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v and v.strip() else None
