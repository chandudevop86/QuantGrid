import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ openPositions: vi.fn(), closedPositions: vi.fn(), positionSummary: vi.fn(), exitPosition: vi.fn(), settleOptionPaper: vi.fn() }));
vi.mock("../api", () => ({ api }));

import PaperTrades from "./PaperTrades";
import * as roles from "../roles";

describe("position lifecycle", () => {
  beforeEach(() => {
    api.openPositions.mockResolvedValue({ positions: [{ id: 7, broker_order_id: "P-7", symbol: "NIFTY 21 JUL 24000 CALL", side: "BUY", product: "INTRADAY", quantity: 65, entry_price: 100, current_price: 110, stop_loss: 90, target: 120, open_pnl: 650 }] });
    api.closedPositions.mockResolvedValue({ positions: [{ id: 6, symbol: "NIFTY 14 JUL 24500 CALL", side: "BUY", product: "INTRADAY", quantity: 65, entry_price: 80, exit_price: 75, closed_pnl: -325, status: "closed", closed_at: "2026-07-14T10:30:00Z" }] });
    api.positionSummary.mockResolvedValue({ open_positions: 1, closed_positions: 1, current_exposure: 7150, unrealized_pnl: 650, realized_pnl: -325, todays_pnl: 325 });
    api.exitPosition.mockResolvedValue({ status: "closed" });
  });

  it("requires confirmation and closes the selected position through the exit API", async () => {
    render(<PaperTrades />);
    const closeButton = await screen.findByRole("button", { name: "Close NIFTY 21 JUL 24000 CALL" });
    fireEvent.click(closeButton);
    expect(screen.getByRole("dialog", { name: "Close NIFTY 21 JUL 24000 CALL position?" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Confirm close" }));
    await waitFor(() => expect(api.exitPosition).toHaveBeenCalledWith(7, { reason: "manual_exit", exit_price: 110 }));
    expect(await screen.findByText("NIFTY 21 JUL 24000 CALL closed successfully.")).toBeVisible();
  });

  it("shows broker-style summary, separate books, and filters both by P&L", async () => {
    render(<PaperTrades />);
    expect(await screen.findByRole("table", { name: "Open positions" })).toBeVisible();
    expect(screen.getByRole("table", { name: "Closed positions" })).toBeVisible();
    expect(screen.getByLabelText("Position summary")).toHaveTextContent("₹325.00");
    expect(screen.getByText("NIFTY 21 JUL 24000 CALL")).toBeVisible();
    expect(screen.getByText("NIFTY 14 JUL 24500 CALL")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "In loss" }));
    expect(screen.queryByText("NIFTY 21 JUL 24000 CALL")).not.toBeInTheDocument();
    expect(screen.getByText("NIFTY 14 JUL 24500 CALL")).toBeVisible();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search positions" }), { target: { value: "does-not-exist" } });
    expect(screen.getByText("No open positions match this filter")).toBeVisible();
    expect(screen.getByText("No closed positions match this filter")).toBeVisible();
  });

  it("requires reviewed evidence before an operator can settle an expired paper option", async () => {
    const role = vi.spyOn(roles,"getCurrentRole").mockReturnValue("admin");
    api.openPositions.mockResolvedValue({positions:[{id:-1,option_order_id:1,symbol:"NIFTY expired CE",side:"BUY",
      quantity:65,entry_price:50,recovery_reason:"expired_contract_requires_verified_settlement"}]});
    api.settleOptionPaper.mockResolvedValue({position:{status:"closed"}});
    try {
      render(<PaperTrades/>);
      fireEvent.click(await screen.findByRole("button",{name:"Review settlement"}));
      const record=screen.getByRole("button",{name:"Record paper settlement"});
      expect(record).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Final underlying settlement price"),{target:{value:"24900"}});
      fireEvent.change(screen.getByLabelText("Official settlement evidence reference"),{target:{value:"Reviewed exchange settlement record"}});
      expect(record).toBeDisabled();
      fireEvent.click(screen.getByRole("checkbox",{name:"I reviewed the final settlement evidence for this expiry."}));
      fireEvent.click(record);
      await waitFor(()=>expect(api.settleOptionPaper).toHaveBeenCalledWith(1,{
        final_underlying_price:24900,evidence_reference:"Reviewed exchange settlement record",confirmed_final_settlement:true,
      }));
    } finally {
      role.mockRestore();
    }
  });
});
