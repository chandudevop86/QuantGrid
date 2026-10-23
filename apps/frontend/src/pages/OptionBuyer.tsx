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
  const quoteTime = typeof rawTimestamp === "string" && /(?:Z|[+-]\\d{2}:\\d{2})$/i.test(rawTimestamp) ? Date.parse(rawTimestamp) : NaN;
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
  const ordered = useMemo(() => [...rows].filter(row => Number.isFinite(row.strike)).sort((a,b) => a.strike-b.strike), [rows]);
  const selected = ordered.find(row => row.strike === chosen) ?? ordered.reduce<OptionBuyerRow | null>((best, row) => !best || Math.abs(row.strike-spot) < Math.abs(best.strike-spot) ? row : best, null);
  const strike = selected?.strike ?? 0;
  const leg = side === "CE" ? selected?.ce : selected?.pe;
  const check = screenBuyerContract(spot, strike, side, leg, providerReady, refreshedAt);
  const price = check.ask;
  const intrinsic = Math.max(0, side === "CE" ? spot-strike : strike-spot);
  return <section className="dashboard-section" aria-label="NIFTY option buyer">
    <div className="section-header"><div><span className="page-eyebrow">Research / paper-only</span><h2>NIFTY Option Buyer</h2><p>Choose a contract and inspect risk. No broker order is sent from this panel.</p></div></div>
    <div role="group" aria-label="Option direction">
      <button type="button" aria-pressed={side==="CE"} onClick={()=>{setSide("CE");setPreview(null);}}>Buy CE</button>{" "}
      <button type="button" aria-pressed={side==="PE"} onClick={()=>{setSide("PE");setPreview(null);}}>Buy PE</button>
    </div>
    <p>Spot: {Number.isFinite(spot) && spot>0 ? spot.toLocaleString("en-IN") : "Unavailable"} · Expiry: {expiry || "Unavailable"}</p>
    <label htmlFor="buyer-strike">Strike</label>{" "}
    <select id="buyer-strike" value={strike || ""} onChange={event=>{setChosen(Number(event.target.value));setPreview(null);}}>
      {!selected && <option value="">No verified contracts</option>}
      {ordered.map(row=><option key={row.strike} value={row.strike}>{row.strike} · {classifyOption(spot,row.strike,side)}</option>)}
    </select>
    <div className="metric-grid" aria-label="Buyer contract details">
      <div className="metric-card"><span className="metric-label">Moneyness</span><strong>{check.category}</strong></div>
      <div className="metric-card"><span className="metric-label">Ask / Bid</span><strong>{price ?? "-"} / {check.bid ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">Intrinsic value</span><strong>{intrinsic.toFixed(2)}</strong></div>
      <div className="metric-card"><span className="metric-label">Delta / Gamma</span><strong>{check.delta ?? "-"} / {numeric(leg?.greeks?.gamma ?? leg?.gamma) ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">Theta / Vega</span><strong>{numeric(leg?.greeks?.theta ?? leg?.theta) ?? "-"} / {numeric(leg?.greeks?.vega ?? leg?.vega) ?? "-"}</strong></div>
      <div className="metric-card"><span className="metric-label">IV / OI</span><strong>{numeric(leg?.iv ?? leg?.implied_volatility) ?? "-"} / {check.oi ?? "-"}</strong></div>
    </div>
    <p role="status">{check.eligible ? "Screening passed (not a trade recommendation)" : "Screening blocked"}</p>
    {check.reasons.length>0 && <ul aria-label="Contract rejection reasons">{check.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}
    <label htmlFor="buyer-lots">Paper lots (preview)</label>{" "}
    <input id="buyer-lots" type="number" min={1} max={10} step={1} value={lots} onChange={e=>setLots(Math.max(1,Math.min(10,Math.trunc(Number(e.target.value)||1))))}/>
    <p>Maximum option premium loss: {price===null ? "Unavailable" : `₹${(price*lots).toFixed(2)} × exchange lot size`} plus costs.</p>
    <button type="button" disabled={!providerReady || !selected || previewBusy} onClick={() => {
      setPreview(null); setPreviewError(null); setPreviewBusy(true);
      api.optionBuyerPreview(strike, side)
        .then(setPreview)
        .catch((err: any) => setPreviewError(err?.response?.data?.detail ?? "Provider preview unavailable"))
        .finally(() => setPreviewBusy(false));
    }}>{previewBusy ? "Verifying…" : "Verify contract with server"}</button>
    {previewError && <p role="alert">{previewError}</p>}
    {preview && <p role="status">Provider contract ID (not exchange-master verified): {preview.security_id}. Quote timestamp: {preview.quote_timestamp || "Unavailable"}. {preview.reason}</p>}
    <p>Expiry break-even: {price===null ? "Unavailable" : (side==="CE" ? strike+price : strike-price).toFixed(2)}</p>
    <p role="status">Execution status: Disabled — exchange contract-master verification and authenticated paper-order persistence are not connected.</p>
    <button type="button" disabled title="Paper order submission requires a separately verified server-side paper-only endpoint">Paper order disabled pending backend validation</button>
  </section>;
}
