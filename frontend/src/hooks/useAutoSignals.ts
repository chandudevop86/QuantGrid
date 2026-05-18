import { useEffect, useState } from "react";
import { api } from "../api";

type AutoSignalState = {
  data?: any;
  candles_analyzed?: number;
  updated_at?: string;
  market_data?: {
    source?: string;
    volume_status?: string;
    warning?: string;
  };
  error?: string;
};

export function useAutoSignals(strategy: string | null, interval = 5000) {
  const [signal, setSignal] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!strategy) {
      setSignal(null);
      return;
    }

    let isMounted = true;

    const fetchSignal = async () => {
      try {
        setLoading(true);

        const candleData = await api.candles("NIFTY", "1m");
        const candles = Array.isArray(candleData?.candles) ? candleData.candles : [];
        const result = await api.runSignals({
          strategy_name: strategy,
          symbol: "NIFTY",
          capital: 100000,
          risk_pct: 1,
          rr_ratio: 2,
          candles,
        });

        if (isMounted) {
          setSignal({
            data: result,
            candles_analyzed: candles.length,
            updated_at: new Date().toISOString(),
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
    const id = window.setInterval(fetchSignal, interval);

    return () => {
      isMounted = false;
      window.clearInterval(id);
    };
  }, [strategy, interval]);

  return { signal, loading };
}

export function useStrategySignals(strategies: string[], interval = 5000) {
  const [signalsByStrategy, setSignalsByStrategy] = useState<Record<string, AutoSignalState>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (strategies.length === 0) {
      setSignalsByStrategy({});
      return;
    }

    let isMounted = true;

    const fetchSignals = async () => {
      try {
        setLoading(true);

        const candleData = await api.candles("NIFTY", "1m");
        const candles = Array.isArray(candleData?.candles) ? candleData.candles : [];
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
              candles,
            });

            nextSignals[strategy] = {
              data: result,
              candles_analyzed: candles.length,
              updated_at: updatedAt,
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
    const id = window.setInterval(fetchSignals, interval);

    return () => {
      isMounted = false;
      window.clearInterval(id);
    };
  }, [strategies, interval]);

  return { signalsByStrategy, loading };
}
