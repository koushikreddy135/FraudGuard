from fastapi import APIRouter, HTTPException, status, Request, Response, Depends
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging
import urllib.parse
import httpx

from backend.database import get_db
from backend.schemas import (
    CustomerRegisterRequest,
    LoginRequest,
    AuthResponse,
    ForgotPasswordRequest,
    VerifyOtpRequest,
    ResetPasswordRequest,
    UserResponse
)
from backend.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    generate_secure_otp
)
from backend.config import settings
from backend.email_service import send_otp_email
from backend.middleware import get_current_user

logger = logging.getLogger("fraudguard.auth")
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register/customer", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_customer(req: CustomerRegisterRequest):
    """
    Public registration endpoint for CUSTOMER accounts only.
    Admins cannot be registered here.
    """
    clean_email = req.email.lower().strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
        if cursor.fetchone():
            # Prevent email enumeration or duplicate collision
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists."
            )
        
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        pwd_hash = hash_password(req.password)
        
        cursor.execute("""
            INSERT INTO users (id, email, full_name, password_hash, role, is_active, failed_login_attempts, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'CUSTOMER', 1, 0, ?, ?)
        """, (user_id, clean_email, req.full_name.strip(), pwd_hash, now_str, now_str))
        cursor.execute("""
            INSERT INTO accounts (id, user_id, balance_cents, currency, created_at, updated_at)
            VALUES (?, ?, 1000000, 'USD', ?, ?)
        """, (f"acct_{uuid.uuid4().hex[:12]}", user_id, now_str, now_str))
        
        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'CUSTOMER_REGISTER', ?, ?)
        """, (f"aud_{uuid.uuid4().hex[:12]}", user_id, f"Registered customer {clean_email}", now_str))

    return {
        "id": user_id,
        "email": clean_email,
        "full_name": req.full_name.strip(),
        "role": "CUSTOMER",
        "created_at": now_str
    }

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    """
    Role-aware authentication for Customer and Admin portals.
    Enforces brute-force lockout, role matching, and secure session creation.
    """
    clean_email = req.email.lower().strip()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    ip_addr = request.client.host if request.client else "unknown"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, email, full_name, password_hash, role, is_active, failed_login_attempts, locked_until
            FROM users WHERE email = ?
        """, (clean_email,))
        user = cursor.fetchone()

        if not user:
            # Generic error to prevent enumeration
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        # Check account lockout
        if user["locked_until"]:
            try:
                locked_until_dt = datetime.fromisoformat(user["locked_until"])
                if now < locked_until_dt:
                    diff_mins = int((locked_until_dt - now).total_seconds() / 60) + 1
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Account is temporarily locked due to excessive failed attempts. Please try again in {diff_mins} minutes."
                    )
            except ValueError:
                pass

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Please contact support."
            )

        # Verify password
        if not verify_password(req.password, user["password_hash"]):
            failed_attempts = user["failed_login_attempts"] + 1
            locked_until = None
            if failed_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                locked_until = (now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)).isoformat()
                cursor.execute(
                    "UPDATE users SET failed_login_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                    (failed_attempts, locked_until, now_str, user["id"])
                )
                conn.commit()  # Must commit before raising — HTTPException triggers rollback otherwise
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed login attempts. Account locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes."
                )
            else:
                cursor.execute(
                    "UPDATE users SET failed_login_attempts = ?, updated_at = ? WHERE id = ?",
                    (failed_attempts, now_str, user["id"])
                )
                conn.commit()  # Must commit before raising — HTTPException triggers rollback otherwise
                remaining = settings.MAX_LOGIN_ATTEMPTS - failed_attempts
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid email or password. {remaining} attempt(s) remaining before temporary lockout."
                )

        # Verify Portal Role Match
        # Customer portal only permits CUSTOMER role. Admin portal only permits ADMIN role.
        user_role = user["role"]
        if req.portal_type != user_role:
            if req.portal_type == "ADMIN" and user_role != "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. This account does not possess Administrative privileges."
                )
            elif req.portal_type == "CUSTOMER" and user_role != "CUSTOMER":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrative accounts must use the dedicated Admin Portal."
                )

        # Successful login: reset failed counters
        cursor.execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
            (now_str, user["id"])
        )

        # Create JWT Access Token
        token_payload = {
            "sub": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user_role
        }
        access_token = create_access_token(token_payload)

        # Set secure HTTP-only cookie for defense-in-depth
        response.set_cookie(
            key="fraudguard_session",
            value=access_token,
            httponly=True,
            secure=(settings.ENVIRONMENT != "development"),
            samesite="lax",
            path="/",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, ip_address, details, created_at)
            VALUES (?, ?, 'LOGIN_SUCCESS', ?, ?, ?)
        """, (f"aud_{uuid.uuid4().hex[:12]}", user["id"], ip_addr, f"Successful login to {req.portal_type} portal", now_str))

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user_role
        }
    }

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Generates a secure OTP for password reset.
    Returns generic success response to prevent email enumeration.
    """
    clean_email = req.email.lower().strip()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, full_name, is_active FROM users WHERE email = ?", (clean_email,))
        user = cursor.fetchone()

        if user and user["is_active"]:
            # Check resend cooldown
            cursor.execute("""
                SELECT created_at FROM password_reset_otps
                WHERE user_id = ? AND is_used = 0
                ORDER BY created_at DESC LIMIT 1
            """, (user["id"],))
            latest = cursor.fetchone()
            if latest:
                last_created = datetime.fromisoformat(latest["created_at"])
                if (now - last_created).total_seconds() < settings.OTP_RESEND_COOLDOWN_SECONDS:
                    wait_time = int(settings.OTP_RESEND_COOLDOWN_SECONDS - (now - last_created).total_seconds())
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Please wait {wait_time} seconds before requesting a new code."
                    )

            # Invalidate previous unused OTPs
            cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE user_id = ?", (user["id"],))

            # Generate OTP
            otp = generate_secure_otp(6)
            otp_hash_val = hash_token(otp)
            expires_at = (now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)).isoformat()
            otp_id = f"otp_{uuid.uuid4().hex[:12]}"

            cursor.execute("""
                INSERT INTO password_reset_otps (id, user_id, otp_hash, expires_at, attempts_left, is_used, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (otp_id, user["id"], otp_hash_val, expires_at, settings.MAX_OTP_ATTEMPTS, now_str))

            # Dispatch Email
            send_otp_email(clean_email, user["full_name"], otp)

    # Generic message regardless of whether email exists to prevent enumeration
    return {
        "message": "If an account exists for this email address, a secure verification code has been dispatched."
    }

@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    """
    Validates an OTP without resetting password yet, giving immediate UI feedback.
    """
    clean_email = req.email.lower().strip()
    now = datetime.now(timezone.utc)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code or email.")

        cursor.execute("""
            SELECT id, otp_hash, expires_at, attempts_left, is_used
            FROM password_reset_otps
            WHERE user_id = ? AND is_used = 0
            ORDER BY created_at DESC LIMIT 1
        """, (user["id"],))
        record = cursor.fetchone()

        if not record:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active verification code found. Please request a new code.")

        if record["attempts_left"] <= 0:
            cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (record["id"],))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum verification attempts exceeded. Please request a new code.")

        if now > datetime.fromisoformat(record["expires_at"]):
            cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (record["id"],))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired. Please request a new code.")

        if hash_token(req.otp) != record["otp_hash"]:
            remaining = record["attempts_left"] - 1
            if remaining <= 0:
                cursor.execute("UPDATE password_reset_otps SET attempts_left = 0, is_used = 1 WHERE id = ?", (record["id"],))
            else:
                cursor.execute("UPDATE password_reset_otps SET attempts_left = ? WHERE id = ?", (remaining, record["id"]))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Incorrect verification code. {max(0, remaining)} attempt(s) remaining.")

    return {"message": "Verification code is valid.", "valid": True}

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """
    Resets user password after verifying OTP.
    Invalidates the OTP immediately to prevent replay.
    """
    clean_email = req.email.lower().strip()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE email = ?", (clean_email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request.")

        cursor.execute("""
            SELECT id, otp_hash, expires_at, attempts_left, is_used
            FROM password_reset_otps
            WHERE user_id = ? AND is_used = 0
            ORDER BY created_at DESC LIMIT 1
        """, (user["id"],))
        record = cursor.fetchone()

        if not record:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired or not found.")

        if record["attempts_left"] <= 0:
            cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (record["id"],))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum attempts exceeded. Please request a new code.")

        if now > datetime.fromisoformat(record["expires_at"]):
            cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (record["id"],))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired.")

        if hash_token(req.otp) != record["otp_hash"]:
            remaining = record["attempts_left"] - 1
            if remaining <= 0:
                cursor.execute("UPDATE password_reset_otps SET attempts_left = 0, is_used = 1 WHERE id = ?", (record["id"],))
            else:
                cursor.execute("UPDATE password_reset_otps SET attempts_left = ? WHERE id = ?", (remaining, record["id"]))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

        # OTP verified! Mark as used immediately
        cursor.execute("UPDATE password_reset_otps SET is_used = 1 WHERE id = ?", (record["id"],))

        # Update password hash
        new_pwd_hash = hash_password(req.new_password)
        cursor.execute("""
            UPDATE users SET password_hash = ?, failed_login_attempts = 0, locked_until = NULL, updated_at = ?
            WHERE id = ?
        """, (new_pwd_hash, now_str, user["id"]))

        # Invalidate any active sessions
        cursor.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user["id"],))

        cursor.execute("""
            INSERT INTO audit_logs (id, user_id, action, details, created_at)
            VALUES (?, ?, 'PASSWORD_RESET', 'Password successfully reset via verified OTP', ?)
        """, (f"aud_{uuid.uuid4().hex[:12]}", user["id"], now_str))

    return {"message": "Password updated successfully. You can now log in with your new password."}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Returns profile information for the authenticated user.
    """
    return current_user

@router.post("/logout")
async def logout(response: Response):
    """
    Logs out the current session by clearing the session cookie.
    """
    response.delete_cookie(key="fraudguard_session", path="/", httponly=True, samesite="lax")
    return {"message": "Successfully signed out."}

# ───────────────────────────────────────────────
# GOOGLE OAUTH 2.0 / OPENID CONNECT (OIDC)
# ───────────────────────────────────────────────

@router.get("/oauth/google/url")
async def get_google_oauth_url(response: Response):
    """
    Returns the Google OAuth 2.0 authorization URL and sets a secure CSRF state cookie.
    """
    if not settings.GOOGLE_CLIENT_ID:
        return {
            "configured": False,
            "url": None,
            "message": "Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        }
    
    state = uuid.uuid4().hex
    redirect_uri = settings.GOOGLE_REDIRECT_URI

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    with get_db() as conn:
        conn.execute(
            "DELETE FROM oauth_states WHERE expires_at <= ? OR is_used = 1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.execute("""
            INSERT INTO oauth_states (state, redirect_uri, expires_at, is_used, created_at)
            VALUES (?, ?, ?, 0, ?)
        """, (state, redirect_uri, expires_at, datetime.now(timezone.utc).isoformat()))
    cookie_options = dict(
        value=state,
        httponly=True,
        secure=(settings.ENVIRONMENT != "development"),
        samesite="lax",
        path="/",
        max_age=1800,
    )
    # Exact-key state cookies prevent a second OAuth tab from overwriting
    # the state expected by the first tab.
    response.set_cookie(
        key=f"oauth_state_{state}",
        **cookie_options,
    )
    # Retain the legacy key during a rolling deployment for in-flight logins.
    response.set_cookie(
        key="oauth_state",
        **cookie_options,
    )

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state
    }
    encoded = urllib.parse.urlencode(params)
    google_url = f"https://accounts.google.com/o/oauth2/v2/auth?{encoded}"
    return {
        "configured": True,
        "url": google_url,
        "message": "Redirect to Google authorization URL."
    }

@router.get("/oauth/google/callback")
async def google_oauth_callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None
):
    """
    Handles Google OAuth redirect, validates CSRF state, exchanges code for ID/access tokens,
    verifies identity via OIDC userinfo, provisions or finds CUSTOMER user,
    and redirects user to customer portal with JWT token.
    """
    # 1. Verify CSRF State
    exact_cookie_state = request.cookies.get(f"oauth_state_{state}") if state else None
    legacy_cookie_state = request.cookies.get("oauth_state")
    cookie_state = exact_cookie_state or (
        legacy_cookie_state if state and state == legacy_cookie_state else None
    )
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    cookie_options = dict(
        path="/",
        httponly=True,
        secure=(settings.ENVIRONMENT != "development"),
        samesite="lax",
    )
    if state:
        response.delete_cookie(key=f"oauth_state_{state}", **cookie_options)
        response.delete_cookie(key=f"oauth_redirect_uri_{state}", **cookie_options)
    response.delete_cookie(key="oauth_state", **cookie_options)
    response.delete_cookie(key="oauth_redirect_uri", **cookie_options)

    server_state = None
    if state:
        with get_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            server_state = conn.execute(
                "SELECT state, redirect_uri, expires_at, is_used "
                "FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            if server_state:
                expires_at = datetime.fromisoformat(server_state["expires_at"])
                if datetime.now(timezone.utc) >= expires_at or server_state["is_used"]:
                    server_state = None
                else:
                    conn.execute(
                        "UPDATE oauth_states SET is_used = 1 WHERE state = ?",
                        (state,),
                    )

    exact_cookie_matches = exact_cookie_state is not None and exact_cookie_state == state
    legacy_cookie_matches = legacy_cookie_state is not None and legacy_cookie_state == state
    exact_cookie_conflicts = exact_cookie_state is not None and exact_cookie_state != state
    cookie_matches = exact_cookie_matches or legacy_cookie_matches
    if (
        not state
        or (server_state is None and not cookie_matches)
        or exact_cookie_conflicts
    ):
        err_msg = urllib.parse.quote("Invalid or expired OAuth state parameter (CSRF protection). Please try again.")
        return RedirectResponse(url=f"/login?oauth_error={err_msg}")

    if error or not code:
        err_msg = urllib.parse.quote(error or "Authorization code missing from Google")
        return RedirectResponse(url=f"/login?oauth_error={err_msg}")
    
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        err_msg = urllib.parse.quote("Google OAuth client is not configured on this server")
        return RedirectResponse(url=f"/login?oauth_error={err_msg}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 2. Exchange authorization code for tokens
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )
            if token_resp.status_code != 200:
                logger.error(f"Google token exchange failed: {token_resp.text}")
                err_msg = urllib.parse.quote("Failed to exchange authorization code with Google.")
                return RedirectResponse(url=f"/login?oauth_error={err_msg}")
            
            token_data = token_resp.json()
            access_token_google = token_data.get("access_token")
            
            # 3. Fetch verified userinfo from Google OIDC endpoint
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token_google}"}
            )
            if userinfo_resp.status_code != 200:
                err_msg = urllib.parse.quote("Failed to fetch verified user profile from Google.")
                return RedirectResponse(url=f"/login?oauth_error={err_msg}")
            
            google_user = userinfo_resp.json()
            email = google_user.get("email", "").lower().strip()
            name = google_user.get("name") or google_user.get("given_name") or email.split("@")[0]
            
            if not email:
                err_msg = urllib.parse.quote("No email returned from Google.")
                return RedirectResponse(url=f"/login?oauth_error={err_msg}")
            
            now_str = datetime.now(timezone.utc).isoformat()
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, email, full_name, role, is_active FROM users WHERE email = ?", (email,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Enforce role isolation: Google OAuth is strictly for CUSTOMER accounts!
                    if existing_user["role"] != "CUSTOMER":
                        err_msg = urllib.parse.quote("Administrative accounts cannot sign in via public Google OAuth.")
                        return RedirectResponse(url=f"/login?oauth_error={err_msg}")
                    
                    if not existing_user["is_active"]:
                        err_msg = urllib.parse.quote("Account has been deactivated. Contact security support.")
                        return RedirectResponse(url=f"/login?oauth_error={err_msg}")
                    
                    user_id = existing_user["id"]
                    full_name = existing_user["full_name"]
                    cursor.execute("""
                        INSERT INTO audit_logs (id, user_id, action, details, created_at)
                        VALUES (?, ?, 'GOOGLE_OAUTH_LOGIN', 'Signed in via Google OAuth 2.0', ?)
                    """, (f"aud_{uuid.uuid4().hex[:12]}", user_id, now_str))
                else:
                    # Auto-provision new CUSTOMER
                    user_id = f"usr_{uuid.uuid4().hex[:12]}"
                    random_pwd_hash = hash_password(f"OAUTH_{uuid.uuid4().hex}")
                    cursor.execute("""
                        INSERT INTO users (id, email, full_name, password_hash, role, is_active, failed_login_attempts, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'CUSTOMER', 1, 0, ?, ?)
                    """, (user_id, email, name, random_pwd_hash, now_str, now_str))
                    cursor.execute("""
                        INSERT INTO accounts (id, user_id, balance_cents, currency, created_at, updated_at)
                        VALUES (?, ?, 1000000, 'USD', ?, ?)
                    """, (f"acct_{uuid.uuid4().hex[:12]}", user_id, now_str, now_str))
                    
                    cursor.execute("""
                        INSERT INTO audit_logs (id, user_id, action, details, created_at)
                        VALUES (?, ?, 'GOOGLE_OAUTH_REGISTER', 'Created new customer account via Google OAuth 2.0', ?)
                    """, (f"aud_{uuid.uuid4().hex[:12]}", user_id, now_str))
                    full_name = name
                
                # Create FraudGuard JWT
                token_payload = {
                    "sub": user_id,
                    "email": email,
                    "full_name": full_name,
                    "role": "CUSTOMER"
                }
                fg_token = create_access_token(token_payload)
            
            redirect = RedirectResponse(url=f"/auth/callback?token={fg_token}")
            redirect.set_cookie(
                key="fraudguard_session",
                value=fg_token,
                httponly=True,
                secure=(settings.ENVIRONMENT != "development"),
                samesite="lax",
                path="/",
                max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            return redirect
            
    except Exception as e:
        logger.error(f"Google OAuth callback unexpected error: {str(e)}")
        err_msg = urllib.parse.quote("An unexpected error occurred during Google authentication.")
        return RedirectResponse(url=f"/login?oauth_error={err_msg}")

