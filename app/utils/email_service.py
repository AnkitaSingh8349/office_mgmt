# app/utils/email_service.py
from dotenv import load_dotenv
load_dotenv()   # ensure .env is read (safe to call multiple times)

import os
import smtplib
import ssl
import logging
from email.message import EmailMessage

# basic logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Helper to format From header
def _format_from(from_email: str, from_name: str = ""):
    if from_name:
        return f"{from_name} <{from_email}>"
    return from_email

def _get_smtp_config():
    """Read SMTP config from environment at call time (fresh values)."""
    return {
        "host": os.getenv("SMTP_HOST"),
        "port": int(os.getenv("SMTP_PORT") or 587),
        "user": os.getenv("SMTP_USER"),
        "pass": os.getenv("SMTP_PASS"),
        "from_email": os.getenv("FROM_EMAIL") or os.getenv("SMTP_USER"),
        "from_name": os.getenv("FROM_NAME") or "",
        "admin_email": os.getenv("ADMIN_EMAIL")
    }

def send_email(to_email: str,
               subject: str,
               body: str,
               attachment_path: str = None,
               reply_to: str = None,
               html: str = None):
    """
    Send an email using SMTP settings from environment.
    Returns True on success, raises RuntimeError on failure.
    """

    cfg = _get_smtp_config()
    SMTP_HOST = cfg["host"]
    SMTP_PORT = cfg["port"]
    SMTP_USER = cfg["user"]
    SMTP_PASS = cfg["pass"]
    FROM_EMAIL = cfg["from_email"]
    FROM_NAME = cfg["from_name"]

    # DEBUG MODE: If SMTP is not configured, log and return True (so dev flows don't break)
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        log.info("EMAIL DEBUG MODE: SMTP not configured. Would send to %s (subject=%s)", to_email, subject)
        log.info("Environment SMTP_HOST=%s SMTP_USER=%s FROM_EMAIL=%s ADMIN_EMAIL=%s", SMTP_HOST, SMTP_USER, FROM_EMAIL, cfg["admin_email"])
        log.info("Body: %s", body)
        return True

    msg = EmailMessage()
    msg["From"] = _format_from(FROM_EMAIL, FROM_NAME)
    msg["To"] = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to

    # plain text body
    msg.set_content(body)

    # optional HTML alternative
    if html:
        msg.add_alternative(html, subtype="html")

    # Attachment handling (assumes PDF if provided)
    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="application",
                    subtype="pdf",
                    filename=os.path.basename(attachment_path)
                )
        except Exception as e:
            raise RuntimeError(f"Attachment error: {e}")

    context = ssl.create_default_context()

    try:
        # If port 465 use implicit SSL
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
                smtp.set_debuglevel(1)
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.set_debuglevel(1)
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.send_message(msg)

        log.info("Email sent to %s (subject: %s)", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError as e:
        log.exception("SMTP Authentication failed")
        # give actionable error for devs
        raise RuntimeError("SMTP Authentication failed. Check SMTP_USER or SMTP_PASS (use Zoho app password).") from e
    except Exception as e:
        log.exception("Email sending failed")
        raise RuntimeError(f"Email sending failed: {e}") from e


def send_email_with_attachment(to_email: str,
                               subject: str,
                               body: str,
                               attachment_path: str = None,
                               reply_to: str = None,
                               html: str = None):
    """
    Backwards-compatible wrapper for existing code.
    """
    return send_email(
        to_email,
        subject,
        body,
        attachment_path=attachment_path,
        reply_to=reply_to,
        html=html
    )
