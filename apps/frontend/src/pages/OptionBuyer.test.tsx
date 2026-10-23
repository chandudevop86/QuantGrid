import { describe, expect, it } from "vitest";
import { classifyOption, screenBuyerContract } from "./OptionBuyer";

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
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5} };
    expect(screenBuyerContract(22455,22450,"PE",leg,true,new Date()).eligible).toBe(true);
  });
  it("blocks stale and unverified data", () => {
    const leg = { security_id:"123",bid:{price:100},ask:{price:101},oi:10000,greeks:{delta:-0.5} };
    expect(screenBuyerContract(22455,22450,"PE",leg,false,new Date(Date.now()-60000)).eligible).toBe(false);
  });
});
