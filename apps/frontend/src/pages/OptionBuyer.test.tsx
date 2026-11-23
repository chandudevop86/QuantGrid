import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import OptionBuyer, { classifyOption, screenBuyerContract } from "./OptionBuyer";
import { api } from "../api";

vi.mock("../api", () => ({ api: {optionBuyerPreview: vi.fn(), optionBuyerPaperOrder: vi.fn()} }));

describe("NIFTY option buyer", () => {
  it("classifies calls and puts correctly", () => {
    expect(classifyOption(22455, 22450, "PE")).toBe("ATM");
    expect(classifyOption(22455, 21600, "PE")).toBe("Deep OTM");
    expect(classifyOption(22455, 21600, "CE")).toBe("Deep ITM");
    expect(classifyOption(22455, 22600, "PE")).toBe("ITM");
  });
  it("blocks missing quotes and Greeks", () => {
    expect(screenBuyerContract(22455, 22450, "PE", { oi: 10000 }, true, new Date()).eligible).toBe(false);
  });
  it("blocks deep OTM even with liquid quotes", () => {
    const leg = { security_id: "123", bid: {price:2}, ask:{price:2.02}, oi:10000, greeks:{delta:-0.4} };
    expect(screenBuyerContract(22455,21600,"PE",leg,true,new Date()).reasons).toContain("Strike category excluded by default policy");
  });
  it("passes complete fresh eligible paper research data", () => {
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5},quote_timestamp:new Date().toISOString() };
    expect(screenBuyerContract(22455,22450,"PE",leg,true,new Date()).eligible).toBe(true);
  });

  it("accepts fresh IST offset timestamps", () => {
    const timestamp = new Date(Date.now() - 5000 + 330 * 60000)
      .toISOString()
      .slice(0, 19) + "+05:30";

    const leg = {
      security_id: "123",
      bid: { price: 100 },
      ask: { price: 101 },
      oi: 10000,
      greeks: { delta: -0.5 },
      quote_timestamp: timestamp,
    };

    expect(
      screenBuyerContract(22455, 22450, "PE", leg, true)
        .eligible
    ).toBe(true);
  });

  it("blocks missing exchange quote timestamps even after a fresh UI refresh", () => {
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5} };
    expect(screenBuyerContract(22455,22450,"PE",leg,true,new Date()).reasons).toContain("Exchange quote timestamp missing, future or older than 30 seconds");
  });
  it("blocks stale exchange quotes even with valid contract fields", () => {
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5},quote_timestamp:new Date(Date.now()-60000).toISOString() };
    expect(screenBuyerContract(22455,22450,"PE",leg,true,new Date()).reasons).toContain("Exchange quote timestamp missing, future or older than 30 seconds");
  });
  it("blocks stale and unverified data", () => {
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5} };
    expect(screenBuyerContract(22455,22450,"PE",leg,false,new Date(Date.now()-60000)).eligible).toBe(false);
  });

  it("submits the verified paper contract with a stable request key", async () => {
    const leg = {security_id:"123",bid:{price:49},ask:{price:50},oi:10000,greeks:{delta:-0.5}};
    vi.mocked(api.optionBuyerPreview).mockResolvedValue({strike:25000,side:"PE",security_id:"123",expiry:"2099-12-31",lot_size:65,
      quote:{bid:49,ask:50},quote_timestamp:new Date().toISOString(),paper_order_enabled:true});
    vi.mocked(api.optionBuyerPaperOrder).mockResolvedValue({option_order_id:7,order:{quantity:65,price:50}});
    render(<OptionBuyer spot={25000} rows={[{strike:25000,pe:leg}]} providerReady={true}/>);
    expect(screen.getByRole("button",{name:"Paper Buy"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button",{name:"Verify contract with server"}));
    await waitFor(()=>expect(screen.getByRole("button",{name:"Paper Buy"})).toBeEnabled());
    fireEvent.click(screen.getByRole("button",{name:"Paper Buy"}));
    await waitFor(()=>expect(api.optionBuyerPaperOrder).toHaveBeenCalledWith(expect.objectContaining({
      side:"PE",strike:25000,lots:1,execution_mode:"paper",idempotency_key:expect.any(String),
    })));
    expect(await screen.findByText(/Paper order 7 recorded/)).toBeVisible();
  });

  it("cannot submit an old preview after the direction changes", async () => {
    let resolvePreview: (value:any)=>void = ()=>{};
    vi.mocked(api.optionBuyerPreview).mockReturnValue(new Promise(resolve=>{resolvePreview=resolve;}));
    const leg={security_id:"123",bid:{price:49},ask:{price:50},oi:10000,greeks:{delta:-0.5}};
    render(<OptionBuyer spot={25000} rows={[{strike:25000,pe:leg,ce:{...leg,greeks:{delta:0.5}}}]} providerReady={true}/>);
    fireEvent.click(screen.getByRole("button",{name:"Verify contract with server"}));
    fireEvent.click(screen.getByRole("button",{name:"Buy CE"}));
    resolvePreview({strike:25000,side:"PE",security_id:"123",lot_size:65,quote:{bid:49,ask:50},
      quote_timestamp:new Date().toISOString(),paper_order_enabled:true});
    await waitFor(()=>expect(screen.getByRole("button",{name:"Verify contract with server"})).toBeEnabled());
    expect(screen.getByRole("button",{name:"Paper Buy"})).toBeDisabled();
  });
});
