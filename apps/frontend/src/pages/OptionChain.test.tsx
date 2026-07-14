import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ optionChain: vi.fn(), historicalOptionChain: vi.fn() }));
vi.mock("../api", () => ({ api }));

import OptionChain from "./OptionChain";

function rows() {
  return Array.from({ length: 25 }, (_, index) => {
    const strike = 23900 + index * 50;
    return {
      strike,
      ce: { ltp: 100 + index, change: index - 12, oi: 1000 + index, change_oi: index * 10, volume: 500 + index, iv: 12.5 },
      pe: { ltp: 120 - index, change: 12 - index, oi: 1200 + index, change_oi: index * -5, volume: 600 + index, iv: 13.2 },
    };
  });
}

describe("NIFTY option chain", () => {
  beforeEach(() => {
    api.optionChain.mockResolvedValue({ source: "dhan-option-chain", symbol: "NIFTY", underlying_price: 24502.4, atm_strike: 24500, expiry: "30 Jul 2026", pcr: 1.08, max_pain: 24500, support: 24400, resistance: 24600, rows: rows() });
    api.historicalOptionChain.mockResolvedValue({ source: "dhan", snapshots: [] });
  });

  it("renders a broker-style calls/strike/puts ladder and changes the strike window", async () => {
    render(<OptionChain />);
    await screen.findByRole("heading", { name: "NIFTY Option Chain" });
    const table = screen.getByRole("table", { name: "NIFTY option chain calls and puts" });
    expect(within(table).getByRole("columnheader", { name: "CALLS" })).toHaveAttribute("colspan", "5");
    expect(within(table).getByRole("columnheader", { name: "PUTS" })).toHaveAttribute("colspan", "5");
    expect(within(table).getByText("ATM")).toBeVisible();
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(13));
    fireEvent.click(screen.getByRole("button", { name: "ATM ±10" }));
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(23));
  });
});
