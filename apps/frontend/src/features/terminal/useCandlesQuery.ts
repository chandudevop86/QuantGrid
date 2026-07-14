import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import type { Timeframe } from "./types";

export type MarketCandle = { timestamp: string; open: number; high: number; low: number; close: number; volume?: number };

export function useCandlesQuery(symbol: string, timeframe: Timeframe) {
  return useQuery({
    queryKey: ["market", "candles", symbol, timeframe],
    queryFn: async (): Promise<MarketCandle[]> => {
      const response = await api.candles(symbol, timeframe);
      return Array.isArray(response?.candles) ? response.candles : [];
    },
    staleTime: 10_000,
    refetchInterval: 30_000,
    retry: 1,
  });
}
