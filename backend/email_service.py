import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from backend.config import settings

logger = logging.getLogger("fraudguard.email")

def send_otp_email(recipient_email: str, recipient_name: str, otp_code: str) -> bool:
    """
    Sends OTP email to the user.
    If SMTP_ENABLED is False (development/testing mode), logs cleanly without exposing credentials
    or failing the user flow.
    """
    subject = "FraudGuard Security: Your Verification Code"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
            .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 36px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
            .brand {{ font-size: 20px; font-weight: 700; color: #164E63; letter-spacing: -0.5px; margin-bottom: 24px; display: flex; align-items: center; gap: 8px; }}
            .otp-box {{ background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 20px; text-align: center; margin: 28px 0; }}
            .otp-code {{ font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #0f172a; font-family: monospace; }}
            .footer {{ margin-top: 32px; font-size: 13px; color: #64748b; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="brand">
                <span>🛡️</span> FraudGuard Security
            </div>
            <h2 style="margin-top:0; color:#0f172a; font-size:20px;">Password Reset Verification</h2>
            <p>Hello {recipient_name},</p>
            <p>We received a request to reset your FraudGuard account password. Use the verification code below to complete the reset. This code is valid for <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.</p>
            <div class="otp-box">
                <div class="otp-code">{otp_code}</div>
            </div>
            <p>If you did not initiate this password reset, please secure your account immediately or notify your security administrator.</p>
            <div class="footer">
                FraudGuard Intelligent Financial Risk & Fraud Monitoring Platform.<br>
                This is an automated security transmission. Do not reply to this email.
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    FraudGuard Security Verification Code
    
    Hello {recipient_name},
    
    Your verification code for password reset is: {otp_code}
    This code is valid for {settings.OTP_EXPIRE_MINUTES} minutes.
    
    If you did not request this code, please ignore this email.
    """
    
    # In development mode or when SMTP credentials are not configured, simulate delivery safely
    if not settings.SMTP_ENABLED or not settings.SMTP_USER:
        logger.info(f"[DEV EMAIL SERVICE] Sending OTP email to {recipient_email}. OTP Code: [{otp_code}]")
        print(f"\n=======================================================")
        print(f"📧 [DEV EMAIL] To: {recipient_email}")
        print(f"📧 [DEV EMAIL] Subject: {subject}")
        print(f"🔑 [DEV OTP CODE]: >>> {otp_code} <<< (Valid for {settings.OTP_EXPIRE_MINUTES} mins)")
        print(f"=======================================================\n")
        return True

    # Real SMTP delivery
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = recipient_email
        
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [recipient_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [recipient_email], msg.as_string())
        
        logger.info(f"OTP successfully delivered via SMTP to {recipient_email}")
        print(f"✅ [SMTP SUCCESS] Real OTP email sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
        print(f"❌ [SMTP ERROR] Could not deliver email to {recipient_email}: {str(e)}")
        return False
