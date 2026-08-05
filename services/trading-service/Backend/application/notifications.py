from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib import request

from Backend.infrastructure.http_safety import require_https_url
from urllib.error import HTTPError
from urllib.error import URLError
import time
from urllib import request

def _post_with_retry(url, payload, retries=3):
    data = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(retries):
        try:
            with request.urlopen(req, timeout=10) as response:
                return response.read()

        except (HTTPError, URLError) as exc:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)            
logger = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}

def _send_telegram(
    settings: NotificationSettings,
    message: str
) -> None:

    url = (
        f"https://api.telegram.org/"
        f"bot{settings.telegram_bot_token}"
        "/sendMessage"
    )

    _post_with_retry(
        url,
        {
            "chat_id": settings.telegram_chat_id,
            "text": message,
        },
    )
@dataclass(frozen=True)
class NotificationSettings:
    enabled: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    slack_webhook_url: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from: str | None
    smtp_to: list[str]
    smtp_use_tls: bool

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from and self.smtp_to)


def get_notification_settings() -> NotificationSettings:
    smtp_to = [
        item.strip()
        for item in (os.getenv("QUANTGRID_SMTP_TO") or os.getenv("SMTP_TO") or "").split(",")
        if item.strip()
    ]
    return NotificationSettings(
        enabled=_truthy(os.getenv("QUANTGRID_ALERTS_ENABLED", "true")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("QUANTGRID_TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("QUANTGRID_TELEGRAM_CHAT_ID"),
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL") or os.getenv("QUANTGRID_SLACK_WEBHOOK_URL"),
        smtp_host=os.getenv("QUANTGRID_SMTP_HOST") or os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("QUANTGRID_SMTP_PORT") or os.getenv("SMTP_PORT") or "587"),
        smtp_username=os.getenv("QUANTGRID_SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("QUANTGRID_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("QUANTGRID_SMTP_FROM") or os.getenv("SMTP_FROM"),
        smtp_to=smtp_to,
        smtp_use_tls=_truthy(os.getenv("QUANTGRID_SMTP_USE_TLS", os.getenv("SMTP_USE_TLS", "true"))),
    )


def _post_json(url: str, payload: dict) -> dict:
    url = require_https_url(
        url,
        allowed_hosts={
            "api.telegram.org",
            "hooks.slack.com",
        },
    )

    data = json.dumps(payload).encode("utf-8")

    http_request = request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(
            http_request,
            timeout=10,
        ) as response:

            body = response.read().decode("utf-8")

            result = json.loads(body)

            if response.status >= 400:
                raise RuntimeError(
                    f"HTTP {response.status}: {body}"
                )

            if result.get("ok") is False:
                raise RuntimeError(
                    result.get("description")
                )

            return result

    except HTTPError as exc:
        raise RuntimeError(
            f"HTTP error {exc.code}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Network error: {exc.reason}"
        ) from exc
        
def _send_slack(settings: NotificationSettings, message: str) -> None:
    _post_json(settings.slack_webhook_url or "", {"text": message})


def _send_email(settings: NotificationSettings, subject: str, message: str) -> None:
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.smtp_from
    email["To"] = ", ".join(settings.smtp_to)
    email.set_content(message)

    with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        try:

            server.send_message(email)

        except smtplib.SMTPException:
            logger.exception("SMTP error")
            raise

        except OSError:
            logger.exception("SMTP connection error")
            raise


def send_alert(subject: str, message: str) -> None:

    settings = get_notification_settings()

    if not settings.enabled:
        return

    channels = [
        (
            "telegram",
            settings.telegram_enabled,
            lambda: _send_telegram(settings, message),
        ),
        (
            "slack",
            settings.slack_enabled,
            lambda: _send_slack(settings, message),
        ),
        (
            "email",
            settings.email_enabled,
            lambda: _send_email(settings, subject, message),
        ),
    ]

    enabled_channels = [
        c for c in channels if c[1]
    ]

    if not enabled_channels:
        logger.warning(
            "Notifications enabled but no delivery channels configured."
        )
        return

    failures = []

    for channel, _, sender in enabled_channels:

        try:

            sender()

            logger.info(
                "Notification delivered via %s",
                channel,
            )

        except Exception as exc:

            logger.exception(
                "Failed sending notification via %s",
                channel,
            )

            failures.append(
                f"{channel}: {exc}"
            )

    if failures:

        raise RuntimeError(
            "Notification delivery failed: "
            + "; ".join(failures)
        )

def alert_job_created(job: dict) -> None:
    send_alert(
        "QuantGrid job queued",
        "\n".join(
            [
                "QuantGrid job queued",
                f"Job: {job.get('job_id')}",
                f"Symbol: {job.get('symbol')}",
                f"Strategy: {job.get('strategy')}",
                f"Status: {job.get('status')}",
            ]
        ),
    )


def alert_job_finished(job: dict) -> None:
    status = str(job.get("status") or "unknown")
    send_alert(
        f"QuantGrid job {status}",
        "\n".join(
            [
                f"QuantGrid job {status}",
                f"Job: {job.get('job_id')}",
                f"Symbol: {job.get('symbol')}",
                f"Strategy: {job.get('strategy')}",
                f"Error: {job.get('error')}" if job.get("error") else "",
            ]
        ).strip(),
    )


def alert_execution_event(result: dict) -> None:
    status = str(result.get("status") or "unknown")
    raw_order = result.get("order")
    order: dict[str, Any] = raw_order if isinstance(raw_order, dict) else {}
    send_alert(
        f"QuantGrid execution {status}",
        "\n".join(
            [
                f"QuantGrid execution {status}",
                f"Mode: {result.get('execution_mode')}",
                f"Source: {result.get('source')}",
                f"Symbol: {order.get('symbol') or result.get('symbol') or '-'}",
                f"Side: {order.get('side') or '-'}",
                f"Quantity: {order.get('quantity') or order.get('qty') or '-'}",
                f"Reason: {result.get('reason') or '-'}",
            ]
        ),
    )
