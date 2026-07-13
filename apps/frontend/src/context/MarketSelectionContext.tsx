import { createContext, useContext, useMemo, useState } from "react";

export const marketInstruments = [
  { symbol: "NIFTY", label: "NIFTY 50" },
  { symbol: "BANKNIFTY", label: "NIFTY Bank" },
  { symbol: "FINNIFTY", label: "NIFTY Financial Services" },
] as const;

export type MarketSymbol = (typeof marketInstruments)[number]["symbol"];

type MarketSelectionValue = {
  symbol: MarketSymbol;
  label: string;
  selectSymbol: (symbol: MarketSymbol) => void;
};

const STORAGE_KEY = "quantgrid-market-symbol";
const MarketSelectionContext = createContext<MarketSelectionValue | null>(null);

function storedSymbol(): MarketSymbol {
  const value = window.localStorage.getItem(STORAGE_KEY);
  return marketInstruments.some((item) => item.symbol === value) ? value as MarketSymbol : "NIFTY";
}

export function MarketSelectionProvider({ children }: { children: React.ReactNode }) {
  const [symbol, setSymbol] = useState<MarketSymbol>(storedSymbol);
  const selectSymbol = (next: MarketSymbol) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setSymbol(next);
  };
  const label = marketInstruments.find((item) => item.symbol === symbol)?.label ?? "NIFTY 50";
  const value = useMemo(() => ({ symbol, label, selectSymbol }), [symbol, label]);
  return <MarketSelectionContext.Provider value={value}>{children}</MarketSelectionContext.Provider>;
}

export function useMarketSelection() {
  const value = useContext(MarketSelectionContext);
  if (!value) throw new Error("useMarketSelection must be used inside MarketSelectionProvider");
  return value;
}
