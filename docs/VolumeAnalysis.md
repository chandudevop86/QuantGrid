# Volume Analysis Engine

`Backend/application/volume_analysis.py` provides deterministic volume intelligence for NIFTY-focused analysis.

It calculates:

- 20 and 50 period volume averages
- Relative volume and volume trend
- Volume spikes
- Breakout and breakdown confirmation
- OBV, VWAP, CMF 21, and Accumulation/Distribution Line
- Volume Profile with POC, VAH, VAL, HVN, and LVN
- Delivery percentage when provided
- Smart money score, volume confidence, signal, reason, and plain-English summary

API:

- `GET /market/volume-analysis?symbol=NIFTY&timeframe=1m`
- `POST /market/volume-analysis`

The POST endpoint accepts mock OHLCV candles and optional delivery data, so tests do not need live market data or broker login. Signals are limited to `BUY`, `SELL`, `WAIT`, and `NO TRADE`; the decision engine remains responsible for final `Buy CE`, `Buy PE`, or `No Trade`.

The decision pipeline delegates its volume checklist to this module through `Backend/application/decision_pipeline.py`. Pipeline callers still use the existing `analyze_volume()` function, but the returned checklist now includes institutional buying/selling, RVOL, smart money score, confidence, and volume profile details.

Compatibility modules exist under `services/trading-service/app/analysis`, `app/models`, and `app/routes` for the requested app-level import paths. They delegate to `Backend/application/volume_analysis.py`, which remains the single source of truth.
