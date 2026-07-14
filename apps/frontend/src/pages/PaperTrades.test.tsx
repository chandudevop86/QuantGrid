import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ paperTrades: vi.fn(), openPositions: vi.fn(), positionSummary: vi.fn(), exitPosition: vi.fn() }));
vi.mock("../api", () => ({ api }));

import PaperTrades from "./PaperTrades";

describe("position lifecycle", () => {
  beforeEach(() => {
    api.paperTrades.mockResolvedValue({ rows: [] });
    api.openPositions.mockResolvedValue({ positions: [{ id: 7, symbol: "NIFTY", side: "BUY", quantity: 65, entry_price: 24000, current_price: 24050, stop_loss: 23950, target: 24100, open_pnl: 3250 }] });
    api.positionSummary.mockResolvedValue({ open_positions: 1 });
    api.exitPosition.mockResolvedValue({ status: "closed" });
  });

  it("requires confirmation and closes the selected position through the exit API", async () => {
    render(<PaperTrades />);
    const closeButton = await screen.findByRole("button", { name: "Close" });
    fireEvent.click(closeButton);
    expect(screen.getByRole("dialog", { name: "Close NIFTY position?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Confirm close" }));
    await waitFor(() => expect(api.exitPosition).toHaveBeenCalledWith(7, { reason: "manual_exit", exit_price: 24050 }));
    expect(await screen.findByText("NIFTY closed successfully.")).toBeVisible();
  });
});
