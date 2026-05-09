import { useEffect, useState } from "react";
import { api } from "../api";

export function useAutoSignals(strategy: string | null, interval = 5000) {
  const [signal, setSignal] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!strategy) return;

    let isMounted = true;

    const fetchSignal = async () => {
      try {
        setLoading(true);

        const result = await api.runSignals({
          strategy,
          data: [
            { open: 100, high: 105, low: 98, close: 103 },
            { open: 103, high: 108, low: 101, close: 107 }
          ]
        });

        if (isMounted) {
          setSignal(result);
        }
      } catch (err) {
        console.error("Signal error:", err);
      } finally {
        setLoading(false);
      }
    };

    // initial call
    fetchSignal();

    // interval polling
    const id = setInterval(fetchSignal, interval);

    return () => {
      isMounted = false;
      clearInterval(id);
    };
  }, [strategy, interval]);

  return { signal, loading };
}