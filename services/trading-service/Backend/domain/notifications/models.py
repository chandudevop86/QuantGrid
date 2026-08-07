from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum


class NotificationStatus(str, Enum):

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"



class NotificationChannel(str, Enum):

    TELEGRAM = "TELEGRAM"
    SLACK = "SLACK"
    EMAIL = "EMAIL"



@dataclass
class NotificationEvent:

    event_type: str

    subject: str

    message: str

    channel: NotificationChannel

    status: NotificationStatus = NotificationStatus.PENDING

    error: str | None = None

    payload: dict | None = None

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    sent_at: datetime | None = None

    id: int | None = None