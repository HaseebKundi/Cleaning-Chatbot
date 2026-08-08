"""
NEW module (didn't exist in the original project). Sends an alert the moment
a lead or complaint comes in — this is the single most important addition
versus the original Support Agent project, per spec section 6.

Design choice: every channel here fails soft. If a client hasn't given you
Twilio/Slack/SMTP credentials yet, notify_* just logs to console instead of
crashing the chat request. That way the bot still works end-to-end during a
demo or before a client has connected their real accounts.
"""
import logging
import smtplib
import threading
from email.mime.text import MIMEText

import httpx

from app.config import settings
from app.models import Lead, SupportTicket

logger = logging.getLogger("notify")
logging.basicConfig(level=logging.INFO)


def _send_sms(body: str) -> bool:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_FROM_NUMBER and settings.OWNER_PHONE_NUMBER):
        return False
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        resp = httpx.post(
            url,
            data={
                "From": settings.TWILIO_FROM_NUMBER,
                "To": settings.OWNER_PHONE_NUMBER,
                "Body": body,
            },
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"SMS notification failed: {e}")
        return False


def _send_slack(body: str) -> bool:
    if not settings.SLACK_WEBHOOK_URL:
        return False
    try:
        resp = httpx.post(settings.SLACK_WEBHOOK_URL, json={"text": body}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")
        return False


def _send_email(subject: str, body: str) -> bool:
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD and settings.OWNER_EMAIL):
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.OWNER_EMAIL
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.warning(f"Email notification failed: {e}")
        return False


def _dispatch(subject: str, body: str) -> None:
    """Try every configured channel; log a clear fallback message if none are set up."""
    sent_via = []
    if _send_sms(body):
        sent_via.append("SMS")
    if _send_slack(body):
        sent_via.append("Slack")
    if _send_email(subject, body):
        sent_via.append("Email")

    if sent_via:
        logger.info(f"Notification sent via: {', '.join(sent_via)}")
    else:
        logger.info(
            "No notification channel configured — set TWILIO_* / SLACK_WEBHOOK_URL / "
            f"SMTP_* in .env. Would have sent:\n{body}"
        )


def _dispatch_async(subject: str, body: str) -> None:
    """Fire the actual sends on a background thread so a slow/hanging SMTP or
    webhook connection can never stall the chat response the customer is
    waiting on. The lead is already saved to the DB by this point — the
    notification is a side effect, not something the user should have to
    wait on.
    """
    threading.Thread(target=_dispatch, args=(subject, body), daemon=True).start()


def notify_new_lead(lead: Lead) -> None:
    kind = "Quote request" if lead.lead_type == "quote_request" else "Booking request"
    lines = [
        f"🧹 New {kind} — {settings.BUSINESS_NAME}",
        f"Name: {lead.name or 'not given'}",
        f"Phone: {lead.phone or 'not given'}",
    ]
    if lead.service_type:
        lines.append(f"Service: {lead.service_type}")
    if lead.home_size:
        lines.append(f"Home size: {lead.home_size}")
    if lead.zip_code:
        lines.append(f"Zip/area: {lead.zip_code}")
    if lead.preferred_datetime:
        lines.append(f"Preferred time: {lead.preferred_datetime}")
    if lead.notes:
        lines.append(f"Notes: {lead.notes}")
    body = "\n".join(lines)
    _dispatch_async(subject=f"New {kind} — {settings.BUSINESS_NAME}", body=body)


def notify_complaint(ticket: SupportTicket) -> None:
    body = (
        f"⚠️ Complaint / needs human — {settings.BUSINESS_NAME}\n"
        f"Session: {ticket.session_id}\n"
        f"Message: {ticket.message}"
    )
    _dispatch_async(subject=f"Complaint escalation — {settings.BUSINESS_NAME}", body=body)
