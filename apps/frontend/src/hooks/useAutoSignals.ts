import { useEffect, useState } from "react";
import { api } from "../api";
import { createSocket } from "../socket";

type AutoSignalState = {
  data?: any;
  diagnostics?: string[];
  raw_response?: any;
  raw_signals?: number;
  validated_signals?: number;
  candles_analyzed?: number;
  updated_at?: string;
  market_data?: {
    source?: string;
    volume_status?: string;
    warning?: string;
  };
  validation_context?: {
    server_time?: string;
    latest_candle_at?: string;
    latest_candle_age_seconds?: number | null;
    max_candle_age_seconds?: number;
    is_recent?: boolean;
  };
  error?: string;
};

type Candle = {
  timestamp?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

function sessionKey(candle: Candle) {
  const timestamp = candle?.timestamp;
  if (!timestamp) return "unknown";
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return String(timestamp).slice(0, 10);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(parsed);
}

function aggregateCandles(candles: Candle[], groupSize: number) {
  const result: Candle[] = [];
  let session: Candle[] = [];
  let currentSession: string | null = null;

  const flushGroup = (group: Candle[]) => {
    if (group.length === 0) return;
    result.push({
      timestamp: group[0]?.timestamp,
      open: Number(group[0]?.open ?? 0),
      high: Math.max(...group.map((candle) => Number(candle.high ?? 0))),
      low: Math.min(...group.map((candle) => Number(candle.low ?? 0))),
      close: Number(group[group.length - 1]?.close ?? 0),
      volume: group.reduce((total, candle) => total + Number(candle.volume ?? 0), 0),
    });
  };

  const flushSession = () => {
    for (let index = 0; index < session.length; index += groupSize) {
      flushGroup(session.slice(index, index + groupSize));
    }
    session = [];
  };

  for (const candle of candles) {
    const key = sessionKey(candle);
    if (currentSession !== null && key !== currentSession) flushSession();
    currentSession = key;
    session.push(candle);
  }
  flushSession();
  return result;
}

function aggregateDailyCandles(candles: Candle[]) {
  const result: Candle[] = [];
  let session: Candle[] = [];
  let currentSession: string | null = null;

  const flushSession = () => {
    if (session.length === 0) return;
    result.push({
      timestamp: session[0]?.timestamp,
      open: Number(session[0]?.open ?? 0),
      high: Math.max(...session.map((candle) => Number(candle.high ?? 0))),
      low: Math.min(...session.map((candle) => Number(candle.low ?? 0))),
      close: Number(session[session.length - 1]?.close ?? 0),
      volume: session.reduce((total, candle) => total + Number(candle.volume ?? 0), 0),
    });
    session = [];
  };

  for (const candle of candles) {
    const key = sessionKey(candle);
    if (currentSession !== null && key !== currentSession) flushSession();
    currentSession = key;
    session.push(candle);
  }
  flushSession();
  return result;
}

async function loadStrategyCandles() {
  // Dhan intraday supports 1m/5m/15m/60m. Build H4 and daily bars from the
  // real 60-minute feed instead of requesting an unsupported "1d" interval.
  const [ltf, m5, m15, h1] = await Promise.all([
    api.candles("NIFTY", "1m", 500),
    api.candles("NIFTY", "5m", 500),
    api.candles("NIFTY", "15m", 500),
    api.candles("NIFTY", "60m", 500),
  ]);

  const candles = Array.isArray(ltf?.candles) ? ltf.candles : [];
  const m5_candles = Array.isArray(m5?.candles) ? m5.candles : [];
  const m15_candles = Array.isArray(m15?.candles) ? m15.candles : [];
  const h1_candles = Array.isArray(h1?.candles) ? h1.candles : [];
  const h4_candles = aggregateCandles(h1_candles, 4);
  const daily_candles = aggregateDailyCandles(h1_candles);

  return {
    candleData: ltf,
    candles,
    m5_candles,
    m15_candles,
    mtf_candles: m15_candles,
    h1_candles,
    h4_candles,
    htf_candles: h1_candles,
    daily_candles,
  };
}

export function useAutoSignals(strategy: string | null, interval = 5000) {
  const [signal, setSignal] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);

  useEffect(() => {
    if (!strategy) {
      setSignal(null);
      return;
    }

    let isMounted = true;

    const fetchSignal = async () => {
      try {
        setLoading(true);

        const {
          candleData,
          candles,
          m5_candles,
          m15_candles,
          mtf_candles,
          h1_candles,
          h4_candles,
          htf_candles,
          daily_candles,
        } = await loadStrategyCandles();
        const result = await api.runSignals({
          strategy_name: strategy,
          symbol: "NIFTY",
          capital: 100000,
          risk_pct: 1,
          rr_ratio: 2,
          include_diagnostics: true,
          candle_source: candleData?.source,
          candles,
          m5_candles,
          m15_candles,
          mtf_candles,
          h1_candles,
          h4_candles,
          htf_candles,
          daily_candles,
        });
        const signals = Array.isArray(result) ? result : result?.signals ?? [];

        if (isMounted) {
          setSignal({
            data: signals,
            diagnostics: Array.isArray(result?.diagnostics) ? result.diagnostics : [],
            raw_response: result,
            raw_signals: typeof result?.raw_signals === "number" ? result.raw_signals : signals.length,
            validated_signals:
              typeof result?.validated_signals === "number" ? result.validated_signals : signals.length,
            candles_analyzed: candles.length,
            updated_at: new Date().toISOString(),
            validation_context: result?.validation_context,
            market_data: {
              source: candleData?.source,
              volume_status: candleData?.volume_status,
              warning: candleData?.warning,
            },
          });
        }
      } catch (error) {
        if (isMounted) setSignal({ error: "Signal API unavailable" });
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchSignal();
    const socket = createSocket();
    socket.onopen = () => {
      if (isMounted) setSocketConnected(true);
    };
    socket.onmessage = () => fetchSignal();
    socket.onclose = () => {
      if (isMounted) setSocketConnected(false);
    };
    socket.onerror = () => {
      if (isMounted) setSocketConnected(false);
    };
    const id = window.setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN) fetchSignal();
    }, interval);

    return () => {
      isMounted = false;
      window.clearInterval(id);
      socket.close();
    };
  }, [strategy, interval]);

  return { signal, loading, socketConnected };
}

export function useStrategySignals(strategies: string[], interval = 5000) {
  const [signalsByStrategy, setSignalsByStrategy] = useState<Record<string, AutoSignalState>>({});
  const [loading, setLoading] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);

  useEffect(() => {
    if (strategies.length === 0) {
      setSignalsByStrategy({});
      return;
    }

    let isMounted = true;

    const fetchSignals = async () => {
      try {
        setLoading(true);

        const { candleData, candles, mtf_candles, htf_candles, daily_candles } = await loadStrategyCandles();
        const updatedAt = new Date().toISOString();
        const nextSignals: Record<string, AutoSignalState> = {};

        await Promise.all(
          strategies.map(async (strategy) => {
            try {
              const result = await api.runSignals({
                strategy_name: strategy,
                symbol: "NIFTY",
                capital: 100000,
                risk_pct: 1,
                rr_ratio: 2,
                include_diagnostics: true,
                candle_source: candleData?.source,
                candles,
                mtf_candles,
                htf_candles,
                daily_candles,
              });
              const signals = Array.isArray(result) ? result : result?.signals ?? [];

              nextSignals[strategy] = {
                data: signals,
                diagnostics: Array.isArray(result?.diagnostics) ? result.diagnostics : [],
                raw_response: result,
                raw_signals: typeof result?.raw_signals === "number" ? result.raw_signals : signals.length,
                validated_signals:
                  typeof result?.validated_signals === "number" ? result.validated_signals : signals.length,
                candles_analyzed: candles.length,
                updated_at: updatedAt,
                validation_context: result?.validation_context,
                market_data: {
                  source: candleData?.source,
                  volume_status: candleData?.volume_status,
                  warning: candleData?.warning,
                },
              };
            } catch {
              nextSignals[strategy] = { error: "Signal API unavailable" };
            }
          })
        );

        if (isMounted) setSignalsByStrategy(nextSignals);
      } catch {
        if (isMounted) {
          setSignalsByStrategy(
            Object.fromEntries(
              strategies.map((strategy) => [
                strategy,
                { error: "Signal API unavailable" },
              ])
            )
          );
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchSignals();
    const socket = createSocket();
    socket.onopen = () => {
      if (isMounted) setSocketConnected(true);
    };
    socket.onmessage = () => fetchSignals();
    socket.onclose = () => {
      if (isMounted) setSocketConnected(false);
    };
    socket.onerror = () => {
      if (isMounted) setSocketConnected(false);
    };
    const id = window.setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN) fetchSignals();
    }, interval);

    return () => {
      isMounted = false;
      window.clearInterval(id);
      socket.close();
    };
  }, [strategies, interval]);

  return { signalsByStrategy, loading, socketConnected };
}
