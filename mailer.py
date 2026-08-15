import os
import smtplib
import threading
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)
SMTP_SECURE = os.environ.get("SMTP_SECURE", "").lower() == "true"
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")

configured = bool(SMTP_HOST)

if not configured:
    print("[shop-crm] SMTP not configured - decision emails will be logged, not sent. See .env.example.", flush=True)


def decision_email(shop_name, customer_name, item_name, status):
    approved = status == "approved"
    if approved:
        subject = f"Your request for {item_name} was approved"
        body = (
            f"Hi {customer_name},\n\n"
            f"Good news - your request for {item_name} has been approved.\n\n"
            f"Get in touch with us to arrange the next step.\n\n"
            f"- {shop_name}"
        )
    else:
        subject = f"Update on your request for {item_name}"
        body = (
            f"Hi {customer_name},\n\n"
            f"Thanks for your interest in {item_name}. We are not able to fulfil "
            f"this request right now.\n\n"
            f"Do reach out if you would like to talk about alternatives.\n\n"
            f"- {shop_name}"
        )
    return subject, body


def _deliver(message, to):
    try:
        if SMTP_SECURE:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            server.starttls()
        with server:
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(message)
    except Exception as err:
        # Never raises to the caller: a mail failure must not turn a successful
        # approval into an error for the shop owner.
        print(f"[shop-crm] email to {to} failed: {err}", flush=True)


def send_decision(to, shop_name, customer_name, item_name, status):
    """Send a decision email. Returns immediately; delivery runs on a thread so
    the owner's approval is not held up by the mail server."""
    if not to:
        return {"sent": False, "reason": "no email on file"}

    subject, body = decision_email(shop_name, customer_name, item_name, status)

    if not configured:
        print(f"[shop-crm] would email {to}: {subject}", flush=True)
        return {"sent": False, "reason": "smtp not configured"}

    message = EmailMessage()
    message["From"] = SMTP_FROM or f"{shop_name} <no-reply@localhost>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    threading.Thread(target=_deliver, args=(message, to), daemon=True).start()
    return {"sent": True}
