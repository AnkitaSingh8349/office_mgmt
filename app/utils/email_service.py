# app/utils/email_service.py
import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")    # set in env or config
SMTP_PASS = os.getenv("SMTP_PASS", "")    # set in env or config
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER or "noreply@example.com")

def send_email_with_attachment(to_email: str, subject: str, body: str, attachment_path: str = None):
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                data = f.read()
                filename = os.path.basename(attachment_path)
            msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
        except Exception as exc:
            raise RuntimeError(f"Failed to attach file: {exc}")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        if SMTP_USER and SMTP_PASS:
            smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)

    return True
