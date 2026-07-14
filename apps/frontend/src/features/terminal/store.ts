import { create } from "zustand";
import type { TerminalTab, Timeframe } from "./types";

type DrawingTool = "cursor" | "trendline" | "horizontal" | "rectangle" | "fib" | "riskReward";

type TerminalState = {
  symbol: string;
  timeframe: Timeframe;
  activeTab: TerminalTab;
  activeDrawing: DrawingTool;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: Timeframe) => void;
  setActiveTab: (tab: TerminalTab) => void;
  setActiveDrawing: (drawing: DrawingTool) => void;
};

/** Shared, UI-only terminal state. Server data belongs in React Query. */
export const useTerminalStore = create<TerminalState>((set) => ({
  symbol: "NIFTY",
  timeframe: "5m",
  activeTab: "positions",
  activeDrawing: "cursor",
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
  setActiveTab: (activeTab) => set({ activeTab }),
  setActiveDrawing: (activeDrawing) => set({ activeDrawing }),
}));
