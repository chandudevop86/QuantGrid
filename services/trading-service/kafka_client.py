from __future__ import annotations

import json
import logging
from typing import Any

try:
    from kafka import KafkaProducer
except ImportError:  # pragma: no cover - depends on optional runtime install
    KafkaProducer = None

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, bootstrap_servers: str = "localhost:9092") -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

        if KafkaProducer is None:
            logger.warning("kafka-python is not installed; events will be logged only")
            return

        try:
            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            )
        except Exception as exc:  # pragma: no cover - depends on local Kafka
            logger.warning("Kafka unavailable at %s: %s", bootstrap_servers, exc)

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        if self._producer is None:
            logger.info("Kafka fallback event topic=%s payload=%s", topic, payload)
            return False

        self._producer.send(topic, payload)
        self._producer.flush()
        return True


publisher = EventPublisher()
