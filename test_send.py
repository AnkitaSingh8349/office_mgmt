from app.utils.email_service import send_email
import os

TO = os.getenv("ADMIN_EMAIL", "ankita@ajxtechnologies.com")
print("Sending test email to", TO)

try:
    ok = send_email(
        TO,
        "TEST EMAIL",
        "This is a test email from backend.\n\nIf you receive this, SMTP is working.",
        reply_to="muskan@ajxtechnologies.com"
    )
    print("send_email returned:", ok)
except Exception as e:
    print("send_email raised exception:", repr(e))

