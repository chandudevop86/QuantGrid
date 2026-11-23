import { useMemo, useState } from "react";
import { api } from "../api";

export type OptionBuyerRow = { strike: number; ce?: any; pe?: any };
export type OptionBuyerProps = {
  spot: number;
  rows: OptionBuyerRow[];
  expiry?: string;
  providerReady: boolean;
  refreshedAt?: Date | null;
};

export function classifyOption(spot: number, strike: number, side: "CE" | "PE") {
  if (!Number.isFinite(spot) || spot <= 0 || !Number.isFinite(strike) || strike <= 0) return "Unavailable";
  const distance = Math.abs(strike - spot) / spot * 100;
  if (distance <= 0.15) return "ATM";
  if (distance <= 0.5) return "Near ATM";
  const itm = side === "CE" ? strike < spot : strike > spot;
  return distance >= 2 ? (itm ? "Deep ITM" : "Deep OTM") : (itm ? "ITM" : "OTM");
}

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function screenBuyerContract(spot: number, strike: number, side: "CE" | "PE", leg: any, providerReady: boolean, refreshedAt?: Date | null) {
  const category = classifyOption(spot, strike, side);
  const bid = numeric(leg?.bid?.price);
  const ask = numeric(leg?.ask?.price);
  const delta = numeric(leg?.greeks?.delta ?? leg?.delta);
  const oi = numeric(leg?.oi);
  const id = String(leg?.security_id ?? leg?.securityId ?? "");
  const reasons: string[] = [];
  if (!providerReady) reasons.push("Verified provider data unavailable");
  if (!["ATM", "Near ATM", "ITM"].includes(category)) reasons.push("Strike category excluded by default policy");
  if (bid === null || ask === null || bid <= 0 || ask < bid) reasons.push("Valid bid/ask missing");
  else if ((ask - bid) / ((ask + bid) / 2) * 100 > 5) reasons.push("Bid/ask spread above 5%");
  if (oi === null || oi < 1000) reasons.push("Open interest below 1,000 or missing");
  if (delta === null || Math.abs(delta) < 0.25 || Math.abs(delta) > 0.85 || (side === "PE" ? delta >= 0 : delta <= 0)) reasons.push("Delta unavailable or outside configured limits");
  // HTTP refresh time is not an exchange quote timestamp. Never substitute it.
  const rawTimestamp = leg?.quote_timestamp;
  const quoteTime = typeof rawTimestamp === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(rawTimestamp) ? Date.parse(rawTimestamp) : NaN;
  const quoteAge = Date.now() - quoteTime;
  if (!Number.isFinite(quoteTime) || quoteAge < 0 || quoteAge > 30000) reasons.push("Exchange quote timestamp missing, future or older than 30 seconds");
  if (!id) reasons.push("Contract security ID missing");
  return { category, reasons, eligible: reasons.length === 0, bid, ask, delta, oi, id };
}

export default function OptionBuyer({ spot, rows, expiry, providerReady, refreshedAt }: OptionBuyerProps) {
  const [side, setSide] = useState<"CE" | "PE">("PE");
  const [chosen, setChosen] = useState<number | null>(null);
  const [lots, setLots] = useState(1);
  const [preview, setPreview] = useState<any>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [orderKey, setOrderKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<any>(null);
  const resetPreview = () => {
    setPreview(null); setPreviewError(null); setOrderKey(null); setSubmitted(null);
  };
  const ordered = useMemo(() => [...rows].filter(row => Number.isFinite(row.strike)).sort((a,b) => a.strike-b.strike), [rows]);
  const selected = ordered.find(row => row.strike === chosen) ?? ordered.reduce<OptionBuyerRow | null>((best, row) => !best || Math.abs(row.strike-spot) < Math.abs(best.strike-spot) ? row : best, null);
  const strike = selected?.strike ?? 0;
  const verifiedPreview = preview?.strike === strike && preview?.side === side ? preview : null;
  const leg = side === "CE" ? selected?.ce : selected?.pe;
  const verifiedLeg = verifiedPreview ? {
    ...leg, security_id: verifiedPreview.security_id, quote_timestamp: verifiedPreview.quote_timestamp,
    bid: {price: verifiedPreview.quote.bid}, ask: {price: verifiedPreview.quote.ask},
  } : leg;
  const check = screenBuyerContract(spot, strike, side, verifiedLeg, providerReady, refreshedAt);
  const price = check.ask;
  const intrinsic = Math.max(0, side === "CE" ? spot-strike : strike-spot);
  return <section className="dashboard-section option-buyer-panel" aria-label="NIFTY option buyer">
    <div className="section-header"><div><span className="page-eyebrow">Research / paper-only</span><h2>NIFTY Option Buyer</h2><p>Choose a contract and inspect risk. No broker order is sent from this panel.</p></div></div>
    <div className="option-buyer-direction" role="group" aria-label="Option direction">
      <button className="option-buyer-side" type="button" aria-pressed={side==="CE"} disabled={submitBusy} onClick={()=>{setSide("CE");resetPreview();}}>Buy CE</button>{" "}
      <button className="option-buyer-side" type="button" aria-pressed={side==="PE"} disabled={submitBusy} onClick={()=>{setSide("PE");resetPreview();}}>Buy PE</button>
    </div>
    <p>Spot: {Number.isFinite(spot) && spot>0 ? spot.toLocaleString("en-IN") : "Unavailable"} · Expiry: {expiry || "Unavailable"}</p>
    <div className="option-buyer-field"><label htmlFor="buyer-strike">Strike</label>
    <select id="buyer-strike" value={strike || ""} disabled={submitBusy} onChange={event=>{setChosen(Number(event.target.value));resetPreview();}}>
      {!selected && <option value="">No verified contracts</option>}
      {ordered.map(row=><option key={row.strike} value={row.strike}>{row.strike} · {classifyOption(spot,row.strike,side)}</option>)}
    </select></div>
    <div className="metric-grid" aria-label="Buyer contract details">
      <div className="metric-card"><span className="metric-label">Moneyness</span><strong>{check.category}</strong></div>
      <div className="metric-card"><span className="metric-label">Ask / Bid</span><strong>{price ?? "-"} / {check.bid ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">Intrinsic value</span><strong>{intrinsic.toFixed(2)}</strong></div>
      <div className="metric-card"><span className="metric-label">Delta / Gamma</span><strong>{check.delta ?? "-"} / {numeric(leg?.greeks?.gamma ?? leg?.gamma) ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">Theta / Vega</span><strong>{numeric(leg?.greeks?.theta ?? leg?.theta) ?? "-"} / {numeric(leg?.greeks?.vega ?? leg?.vega) ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">IV / OI</span><strong>{numeric(leg?.iv ?? leg?.implied_volatility) ?? "-"} / {check.oi ?? "-"}</strong></div>
    </div>
    <p className="option-buyer-screening" role="status">{check.eligible ? "Screening passed (not a trade recommendation)" : "Screening blocked"}</p>
    {check.reasons.length>0 && <ul aria-label="Contract rejection reasons">{check.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}
    <div className="option-buyer-field"><label htmlFor="buyer-lots">Paper lots</label>
    <input id="buyer-lots" type="number" min={1} max={10} step={1} value={lots} disabled={submitBusy} onChange={e=>{setLots(Math.max(1,Math.min(10,Math.trunc(Number(e.target.value)||1))));resetPreview();}}/></div>
    <p>Maximum option premium loss: {verifiedPreview?.lot_size && verifiedPreview?.quote?.ask ? `₹${(verifiedPreview.quote.ask*verifiedPreview.lot_size*lots).toFixed(2)} (${lots} × ${verifiedPreview.lot_size} units)` : price===null ? "Unavailable" : `₹${(price*lots).toFixed(2)} × exchange lot size`} plus costs.</p>
    <button type="button" disabled={!selected || previewBusy || submitBusy} onClick={() => {
      resetPreview(); setPreviewBusy(true);
      api.optionBuyerPreview(strike, side)
        .then((verified: any) => {setPreview(verified);setOrderKey(crypto.randomUUID());})
        .catch((err: any) => setPreviewError(err?.response?.data?.detail ?? "Provider preview unavailable"))
        .finally(() => setPreviewBusy(false));
    }}>{previewBusy ? "Verifying…" : "Verify contract with server"}</button>
    {previewError && <p role="alert">{previewError}</p>}
    {verifiedPreview && <p role="status">Verified contract ID: {verifiedPreview.security_id}. Expiry: {verifiedPreview.expiry}. Lot size: {verifiedPreview.lot_size}. Quote timestamp: {verifiedPreview.quote_timestamp || "Unavailable"}. {verifiedPreview.reason}</p>}
    <p>Expiry break-even: {price===null ? "Unavailable" : (side==="CE" ? strike+price : strike-price).toFixed(2)}</p>
    <p className="option-buyer-execution" role="status">{verifiedPreview?.paper_order_enabled ? "Paper execution available. Price and account risk are checked again when you submit." : "Verify a contract during market hours to enable paper execution."}</p>
    <button type="button" disabled={!verifiedPreview?.paper_order_enabled || !check.eligible || !orderKey || submitBusy || !!submitted} onClick={() => {
      if (!orderKey) return;
      setSubmitBusy(true);setPreviewError(null);
      api.optionBuyerPaperOrder({symbol:"NIFTY",side,strike,lots,execution_mode:"paper",idempotency_key:orderKey})
        .then(setSubmitted)
        .catch((err: any) => setPreviewError(err?.response?.data?.detail ?? "Paper order result unavailable. Retry uses the same request key."))
        .finally(() => setSubmitBusy(false));
    }}>{submitBusy ? "Recording paper order…" : "Paper Buy"}</button>
    {submitted && <p role="status">Paper order {submitted.option_order_id ?? submitted.paper_trade_id} recorded. Quantity: {submitted.order?.quantity}; premium: ₹{submitted.order?.price}. <a href="/paper-trades">View positions</a></p>}
  </section>;
}
