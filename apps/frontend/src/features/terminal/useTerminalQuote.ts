import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

export type TerminalQuote = {
  symbol: string;
  price: number | null;
  changePercent: number | null;
  provider: string | null;
  timestamp: string | null;
  warning: string | null;
};

function asFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normaliseQuote(symbol: string, payload: Record<string, unknown>): TerminalQuote {
  return {
    symbol: String(payload.symbol ?? symbol).toUpperCase(),
    price: asFiniteNumber(payload.ltp ?? payload.price),
    changePercent: asFiniteNumber(payload.change_pct),
    provider: typeof payload.provider === "string" ? payload.provider : null,
    timestamp: typeof payload.timestamp === "string" ? payload.timestamp : null,
    warning: typeof payload.warning === "string" ? payload.warning : typeof payload.provider_warning === "string" ? payload.provider_warning : null,
  };
}

/**
 * The terminal deliberately uses the existing market API instead of fabricating a
 * quote. The API may return its latest stored live tick when the provider is down;
 * its warning remains visible to the trader.
 */
export function useTerminalQuote(symbol: string) {
  return useQuery({
    queryKey: ["market", "ltp", symbol],
    queryFn: async (): Promise<TerminalQuote> => normaliseQuote(symbol, await api.ltp(symbol)),
    staleTime: 4_000,
    refetchInterval: 10_000,
    retry: 1,
  });
}
