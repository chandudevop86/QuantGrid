from __future__ import annotations

from email.message import EmailMessage

from Backend.application import notifications


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"ok"


class _FakeSMTP:
    sent_messages: list[EmailMessage] = []
    logged_in: tuple[str, str] | None = None
    started_tls = False

    def __init__(self, host: str, port: int, timeout: int):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self, context):
        self.started_tls = True

    def login(self, username: str, password: str):
        self.logged_in = (username, password)

    def send_message(self, message: EmailMessage):
        self.sent_messages.append(message)


def test_send_alert_noops_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    calls = []
    monkeypatch.setattr(notifications.request, "urlopen", lambda *_args, **_kwargs: calls.append("called"))

    notifications.send_alert("Subject", "Message")

    assert calls == []


def test_send_alert_posts_to_telegram_and_slack(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/example")

    calls = []

    def fake_urlopen(http_request, timeout):
        calls.append((http_request.full_url, http_request.data.decode("utf-8"), timeout))
        return _FakeResponse()

    monkeypatch.setattr(notifications.request, "urlopen", fake_urlopen)

    notifications.send_alert("Subject", "Message")

    assert len(calls) == 2
    assert calls[0][0] == "https://api.telegram.org/bottoken/sendMessage"
    assert "Message" in calls[0][1]
    assert calls[1][0] == "https://hooks.slack.test/example"
    assert "Message" in calls[1][1]


def test_send_alert_sends_email(monkeypatch):
    _FakeSMTP.sent_messages = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "alerts@example.test")
    monkeypatch.setenv("SMTP_TO", "admin@example.test,ops@example.test")
    monkeypatch.setattr(notifications.smtplib, "SMTP", _FakeSMTP)

    notifications.send_alert("Subject", "Message")

    assert len(_FakeSMTP.sent_messages) == 1
    message = _FakeSMTP.sent_messages[0]
    assert message["Subject"] == "Subject"
    assert message["From"] == "alerts@example.test"
    assert message["To"] == "admin@example.test, ops@example.test"
    assert "Message" in message.get_content()
