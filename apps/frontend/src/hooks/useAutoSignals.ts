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

async function loadStrategyCandles() {
  const [ltf, mtf, htf, daily] = await Promise.all([
    api.candles("NIFTY", "1m"),
    api.candles("NIFTY", "15m"),
    api.candles("NIFTY", "60m"),
    api.candles("NIFTY", "1d"),
  ]);

  return {
    candleData: ltf,
    candles: Array.isArray(ltf?.candles) ? ltf.candles : [],
    mtf_candles: Array.isArray(mtf?.candles) ? mtf.candles : [],
    htf_candles: Array.isArray(htf?.candles) ? htf.candles : [],
    daily_candles: Array.isArray(daily?.candles) ? daily.candles : [],
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

        const { candleData, candles, mtf_candles, htf_candles, daily_candles } = await loadStrategyCandles();
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
