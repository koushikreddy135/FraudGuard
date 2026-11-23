import argparse
import sys
import uuid
import re
from datetime import datetime, timezone
from backend.database import init_db, get_db
from backend.security import hash_password

def bootstrap_admin(email: str, full_name: str, password: str):
    init_db()
    clean_email = email.lower().strip()

    # Password validation
    if len(password) < 8:
        print("❌ Error: Admin password must be at least 8 characters long.")
        sys.exit(1)
    if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"[0-9]", password) and re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)):
        print("❌ Error: Password must contain uppercase, lowercase, number, and special character.")
        sys.exit(1)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, role FROM users WHERE email = ?", (clean_email,))
        existing = cursor.fetchone()
        
        now_str = datetime.now(timezone.utc).isoformat()
        pwd_hash = hash_password(password)

        if existing:
            if existing["role"] == "ADMIN":
                print(f"⚠️ Admin user with email '{clean_email}' already exists. Updating password...")
                cursor.execute("""
                    UPDATE users SET password_hash = ?, full_name = ?, failed_login_attempts = 0, locked_until = NULL, updated_at = ?
                    WHERE id = ?
                """, (pwd_hash, full_name.strip(), now_str, existing["id"]))
                print(f"✅ Admin account '{clean_email}' password updated successfully.")
            else:
                print(f"❌ Error: A customer account exists with email '{clean_email}'. Cannot overwrite with admin privileges.")
                sys.exit(1)
        else:
            admin_id = f"adm_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO users (id, email, full_name, password_hash, role, is_active, failed_login_attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ADMIN', 1, 0, ?, ?)
            """, (admin_id, clean_email, full_name.strip(), pwd_hash, now_str, now_str))
            
            cursor.execute("""
                INSERT INTO audit_logs (id, user_id, action, details, created_at)
                VALUES (?, ?, 'ADMIN_BOOTSTRAP', ?, ?)
            """, (f"aud_{uuid.uuid4().hex[:12]}", admin_id, f"Bootstrapped admin account {clean_email}", now_str))
            
            print(f"✅ Successfully provisioned Admin account '{clean_email}' (ID: {admin_id}).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Secure Admin Provisioning Tool for FraudGuard")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--name", required=True, help="Admin full name")
    parser.add_argument("--password", required=True, help="Strong admin password")
    
    args = parser.parse_args()
    bootstrap_admin(args.email, args.name, args.password)
