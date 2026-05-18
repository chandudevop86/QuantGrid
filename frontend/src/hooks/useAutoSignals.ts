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
