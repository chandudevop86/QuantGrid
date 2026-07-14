import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ latestSignals: vi.fn() }));
vi.mock("../api", () => ({ api }));
import AiScanner from "./AiScanner";

describe("AI Scanner", () => {
  it("ranks live signals and exposes a safe execution handoff", async () => {
    api.latestSignals.mockResolvedValue({ active_signals: [{ id: "signal-1", strategy_name: "breakout", symbol: "NIFTY", side: "BUY", score: 82, timestamp: "2026-07-14T10:00:00Z" }], rejected_signals: [{ signal: { strategy_name: "mean_reversion", symbol: "NIFTY", side: "SELL" }, decision: { score: 41, reason: "Trend conflict" } }], stale_signals: [] });
    render(<MemoryRouter><AiScanner /></MemoryRouter>);
    expect(await screen.findByRole("table", { name: "AI scanner results" })).toBeVisible();
    expect(screen.getByText("breakout")).toBeVisible();
    expect(screen.getByRole("link", { name: "Trade" })).toHaveAttribute("href", "/trade");
    expect(screen.getByText(/not a recommendation/i)).toBeVisible();
  });
});
