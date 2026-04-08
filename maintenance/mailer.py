import base64
import os
import socket
import ssl
import smtplib
import time
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import requests
from .logging_config import logger

def _resolve_ipv4_targets(host, port):
    targets = []
    try:
        infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except Exception:
        return targets
    seen = set()
    for info in infos:
        ip = info[4][0]
        if ip not in seen:
            seen.add(ip)
            targets.append(ip)
    return targets


def _is_network_unreachable_error(exc):
    message = str(exc).lower()
    if "network is unreachable" in message:
        return True
    errno = getattr(exc, "errno", None)
    return errno == 101


def _send_via_smtp(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_addr: str,
    to_addrs,
    subject: str,
    body_md: str,
    json_attachment: Optional[str] = None,
):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = ", ".join(to_addrs)
    msg.attach(MIMEText(body_md, 'plain'))
    if json_attachment:
        part = MIMEApplication(json_attachment, Name="report.json")
        part['Content-Disposition'] = 'attachment; filename="report.json"'
        msg.attach(part)

    max_retries = 3
    ipv4_targets = []
    for attempt in range(max_retries):
        targets = [smtp_host] + ipv4_targets
        for target in targets:
            try:
                if smtp_port == 465:
                    server_ctx = smtplib.SMTP_SSL(
                        target,
                        smtp_port,
                        timeout=10,
                        context=ssl.create_default_context(),
                    )
                    use_starttls = False
                else:
                    server_ctx = smtplib.SMTP(target, smtp_port, timeout=10)
                    use_starttls = True
                with server_ctx as server:
                    if use_starttls:
                        server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                logger.info("Email sent via SMTP to %s", to_addrs)
                return True
            except Exception as e:
                logger.warning(
                    "SMTP attempt %s target=%s failed: %s",
                    attempt + 1,
                    target,
                    e,
                )
                if target == smtp_host and _is_network_unreachable_error(e) and not ipv4_targets:
                    ipv4_targets = _resolve_ipv4_targets(smtp_host, smtp_port)
                    if ipv4_targets:
                        logger.info("SMTP IPv4 fallback targets discovered for host %s", smtp_host)
        if attempt < max_retries - 1:
            time.sleep(5 * (attempt + 1))
    logger.error("All SMTP attempts failed")
    return False


def _send_via_sendgrid(
    *,
    api_key: str,
    from_addr: str,
    to_addrs,
    subject: str,
    body_md: str,
    json_attachment: Optional[str] = None,
):
    if not api_key:
        return False

    effective_from = (os.environ.get("SENDGRID_FROM") or from_addr or "").strip()
    if not effective_from:
        logger.error("SENDGRID_API_KEY is set but no sender configured (SENDGRID_FROM or SMTP_FROM)")
        return False

    payload = {
        "personalizations": [{"to": [{"email": addr} for addr in to_addrs]}],
        "from": {"email": effective_from},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_md}],
    }
    if json_attachment:
        payload["attachments"] = [
            {
                "content": base64.b64encode(json_attachment.encode("utf-8")).decode("ascii"),
                "filename": "report.json",
                "type": "application/json",
                "disposition": "attachment",
            }
        ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://api.sendgrid.com/v3/mail/send"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code in (200, 202):
                logger.info("Email sent via SendGrid to %s", to_addrs)
                return True
            logger.warning(
                "SendGrid attempt %s failed with status=%s body=%s",
                attempt + 1,
                response.status_code,
                (response.text or "")[:500],
            )
        except Exception as exc:
            logger.warning("SendGrid attempt %s failed: %s", attempt + 1, exc)
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))
    return False


def _send_via_resend(
    *,
    api_key: str,
    to_addrs,
    subject: str,
    body_md: str,
    json_attachment: Optional[str] = None,
):
    if not api_key:
        return False

    # Resend sandbox works out-of-the-box with onboarding@resend.dev.
    from_addr = (os.environ.get("RESEND_FROM") or "onboarding@resend.dev").strip()
    payload = {
        "from": from_addr,
        "to": to_addrs,
        "subject": subject,
        "text": body_md,
    }
    if json_attachment:
        payload["attachments"] = [
            {
                "filename": "report.json",
                "content": base64.b64encode(json_attachment.encode("utf-8")).decode("ascii"),
            }
        ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://api.resend.com/emails"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if 200 <= response.status_code < 300:
                logger.info("Email sent via Resend to %s", to_addrs)
                return True
            logger.warning(
                "Resend attempt %s failed with status=%s body=%s",
                attempt + 1,
                response.status_code,
                (response.text or "")[:500],
            )
        except Exception as exc:
            logger.warning("Resend attempt %s failed: %s", attempt + 1, exc)
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))
    return False


def _provider_order():
    default_order = ["sendgrid", "resend", "smtp"]
    preferred = (os.environ.get("EMAIL_PROVIDER") or "").strip().lower()
    if preferred in default_order:
        return [preferred]
    return default_order


def send_email(tenant_config, subject_suffix, body_md, json_attachment=None):
    """Sends email via HTTPS provider (SendGrid/Resend) with SMTP fallback."""
    email_cfg = tenant_config['email']
    subject = f"{email_cfg['subject_prefix']} {subject_suffix}"
    to_addrs = email_cfg.get("to_addrs") or []
    if not to_addrs:
        logger.error("No email recipients configured in tenant email.to_addrs")
        return False

    from_addr = (os.environ.get(email_cfg['from_addr_env_key']) or "").strip()

    sendgrid_api_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    resend_api_key = (os.environ.get("RESEND_API_KEY") or "").strip()

    smtp_host = (os.environ.get(email_cfg['smtp_host_env_key']) or "").strip()
    raw_port = (os.environ.get(email_cfg['smtp_port_env_key']) or "").strip()
    try:
        smtp_port = int(raw_port) if raw_port else 587
    except ValueError:
        logger.warning("Invalid SMTP port value '%s'; using default 587", raw_port)
        smtp_port = 587
    smtp_user = (os.environ.get(email_cfg['smtp_user_env_key']) or "").strip()
    smtp_pass = (os.environ.get(email_cfg['smtp_pass_env_key']) or "").strip()

    for provider in _provider_order():
        if provider == "sendgrid":
            if sendgrid_api_key and _send_via_sendgrid(
                api_key=sendgrid_api_key,
                from_addr=from_addr,
                to_addrs=to_addrs,
                subject=subject,
                body_md=body_md,
                json_attachment=json_attachment,
            ):
                return True
        elif provider == "resend":
            if resend_api_key and _send_via_resend(
                api_key=resend_api_key,
                to_addrs=to_addrs,
                subject=subject,
                body_md=body_md,
                json_attachment=json_attachment,
            ):
                return True
        elif provider == "smtp":
            if all([smtp_host, smtp_user, smtp_pass, from_addr]) and _send_via_smtp(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_pass=smtp_pass,
                from_addr=from_addr,
                to_addrs=to_addrs,
                subject=subject,
                body_md=body_md,
                json_attachment=json_attachment,
            ):
                return True

    logger.error("No email delivery channel succeeded (SendGrid/Resend/SMTP)")
    return False
