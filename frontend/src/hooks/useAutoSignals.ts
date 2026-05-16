import { useEffect, useState } from "react";
import { api } from "../api";

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

        const now = new Date().toISOString();
        const result = await api.runSignals({
          strategy_name: strategy,
          symbol: "NIFTY",
          capital: 100000,
          risk_pct: 1,
          rr_ratio: 2,
          candles: [
            { timestamp: now, open: 100, high: 105, low: 98, close: 103, volume: 1000 },
            { timestamp: now, open: 103, high: 108, low: 101, close: 107, volume: 1200 },
          ],
        });

        if (isMounted) setSignal(result);
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
