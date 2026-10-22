"""Append-only signal evaluations, separate from trade/order journals."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from Backend.core.database import Base


class SignalEvaluationEvent(Base):
    __tablename__ = "signal_evaluation_events"
    __table_args__ = (UniqueConstraint("evaluation_id", "event_type", name="uq_signal_eval_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_time: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_time: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    mtf_bias: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
