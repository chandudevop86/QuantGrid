from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select

from Backend.domain.governance_models import DatasetSnapshot, canonical_json, sha256_text


class DatasetSnapshotError(ValueError):
    pass


def _timestamp(value: Any) -> str:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        raise DatasetSnapshotError("Candle timestamp is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    timestamp = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def _number(value: Any, *, field: str) -> str:
    try:
        decimal = Decimal(str(value))
    except Exception as exc:
        raise DatasetSnapshotError(f"Invalid candle {field}: {value!r}") from exc
    if not decimal.is_finite():
        raise DatasetSnapshotError(f"Invalid candle {field}: {value!r}")
    return format(decimal.normalize(), "f")


def canonical_candles(candles: Iterable[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for candle in candles:
        item = candle if isinstance(candle, dict) else {
            key: getattr(candle, key) for key in ("timestamp", "open", "high", "low", "close", "volume")
        }
        normalized.append(
            {
                "timestamp": _timestamp(item.get("timestamp")),
                "open": _number(item.get("open"), field="open"),
                "high": _number(item.get("high"), field="high"),
                "low": _number(item.get("low"), field="low"),
                "close": _number(item.get("close"), field="close"),
                "volume": _number(item.get("volume", 0), field="volume"),
            }
        )
    if not normalized:
        raise DatasetSnapshotError("Cannot snapshot an empty candle dataset")
    return sorted(normalized, key=lambda row: row["timestamp"])


def dataset_hash(candles: Iterable[Any]) -> str:
    return sha256_text(canonical_json(canonical_candles(candles)))


def create_dataset_snapshot(
    db,
    *,
    candles: Iterable[Any],
    provider: str,
    exchange: str,
    security_identifier: str,
    symbol: str,
    instrument: str,
    timeframe: str,
    timezone_name: str,
    source_metadata: dict[str, Any] | None = None,
) -> DatasetSnapshot:
    rows = canonical_candles(candles)
    content_hash = sha256_text(canonical_json(rows))
    metadata_hash = sha256_text(canonical_json(source_metadata or {}))
    existing = db.scalar(
        select(DatasetSnapshot).where(
            DatasetSnapshot.provider == provider,
            DatasetSnapshot.exchange == exchange,
            DatasetSnapshot.security_identifier == security_identifier,
            DatasetSnapshot.instrument == instrument,
            DatasetSnapshot.timeframe == timeframe,
            DatasetSnapshot.dataset_hash == content_hash,
            DatasetSnapshot.source_metadata_hash == metadata_hash,
        )
    )
    if existing is not None:
        return existing
    snapshot = DatasetSnapshot(
        provider=provider,
        exchange=exchange,
        security_identifier=security_identifier,
        symbol=symbol,
        instrument=instrument,
        timeframe=timeframe,
        timezone=timezone_name,
        start_time=rows[0]["timestamp"],
        end_time=rows[-1]["timestamp"],
        row_count=len(rows),
        dataset_hash=content_hash,
        source_metadata_hash=metadata_hash,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def snapshot_market_candles(
    db,
    *,
    symbol: str,
    timeframe: str,
    provider: str,
    exchange: str,
    security_identifier: str,
    instrument: str,
    timezone_name: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> DatasetSnapshot:
    """Snapshot existing market_candles; it never creates or alters candle records."""
    from Backend.domain.trading_store_models import MarketCandleRecord

    query = select(MarketCandleRecord).where(
        MarketCandleRecord.symbol == symbol.upper(),
        MarketCandleRecord.interval == timeframe,
    )
    if start_time is not None:
        query = query.where(MarketCandleRecord.timestamp >= start_time)
    if end_time is not None:
        query = query.where(MarketCandleRecord.timestamp <= end_time)
    records = db.scalars(query.order_by(MarketCandleRecord.timestamp)).all()
    metadata = {
        "market_symbols": sorted({record.market_symbol for record in records}),
        "providers_observed": sorted({record.source for record in records}),
        "timezones_observed": sorted({record.exchange_timezone or "" for record in records}),
    }
    return create_dataset_snapshot(
        db,
        candles=records,
        provider=provider,
        exchange=exchange,
        security_identifier=security_identifier,
        symbol=symbol.upper(),
        instrument=instrument,
        timeframe=timeframe,
        timezone_name=timezone_name,
        source_metadata=metadata,
    )
