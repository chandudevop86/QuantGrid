import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const refreshMs = 15000;

function formatNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "-";
}

function enrichOptionChain(data: any) {
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const totalCallOi = rows.reduce((sum: number, row: any) => sum + Number(row?.ce?.oi ?? 0), 0);
  const totalPutOi = rows.reduce((sum: number, row: any) => sum + Number(row?.pe?.oi ?? 0), 0);
  const maxPain = rows.length
    ? rows.reduce((best: any, candidate: any) => {
      const candidateStrike = Number(candidate?.strike ?? 0);
      const pain = rows.reduce((sum: number, row: any) => {
        const strike = Number(row?.strike ?? 0);
        return sum
          + Math.max(strike - candidateStrike, 0) * Number(row?.ce?.oi ?? 0)
          + Math.max(candidateStrike - strike, 0) * Number(row?.pe?.oi ?? 0);
      }, 0);
      return pain < best.pain ? { strike: candidateStrike, pain } : best;
    }, { strike: Number(rows[0]?.strike ?? 0), pain: Number.POSITIVE_INFINITY }).strike
    : data?.max_pain;
  const atm = Number(data?.atm_strike ?? 0);
  const step = Number(data?.step ?? 50) || 50;

  return {
    ...data,
    pcr: data?.pcr ?? (totalCallOi > 0 ? Number((totalPutOi / totalCallOi).toFixed(3)) : undefined),
    max_pain: data?.max_pain ?? maxPain,
    greek_model: data?.greek_model ?? "derived delta",
    source: data?.source ?? "market-option-chain",
    rows: rows.map((row: any) => {
      const strike = Number(row?.strike ?? 0);
      const distance = atm && strike ? Math.max(-1, Math.min(1, (atm - strike) / (step * 4))) : 0;
      return {
        ...row,
        ce: { ...row.ce, greeks: row.ce?.greeks ?? { delta: Number((0.5 + distance / 2).toFixed(2)) } },
        pe: { ...row.pe, greeks: row.pe?.greeks ?? { delta: Number((-0.5 + distance / 2).toFixed(2)) } },
      };
    }),
  };
}

export default function OptionChain() {
  const [chain, setChain] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const loadChain = useCallback((showInitialLoading = false) => {
    if (showInitialLoading) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    return api
      .optionChainEngine("NIFTY")
      .catch((err: any) => {
        if (err?.response?.status === 404) {
          return api.optionChain("NIFTY").then(enrichOptionChain);
        }
        throw err;
      })
      .then((data) => {
        setChain(enrichOptionChain(data));
        setLastRefreshed(new Date());
      })
      .catch((err: any) => {
        const message = err?.message === "Network Error"
          ? "Cannot reach the market API. Check that the backend is running on port 8000."
          : err?.response?.data?.detail ?? err?.message ?? "Failed to load option chain.";
        setError(message);
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    void loadChain(true);
    const timer = window.setInterval(() => {
      void loadChain(false);
    }, refreshMs);
    return () => window.clearInterval(timer);
  }, [loadChain]);

  const refreshLabel = lastRefreshed
    ? `Updated ${lastRefreshed.toLocaleTimeString()}`
    : "Auto refresh every 15s";

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Option Chain</h1>
          <p>NIFTY option chain around the current ATM strike.</p>
        </div>
        <button
          type="button"
          className="refresh-button"
          onClick={() => void loadChain(false)}
          disabled={loading || refreshing}
        >
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {chain?.warning && !error && <div className="alert alert-warning" role="status">{chain.warning}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Underlying</span>
          <strong className="metric-value">{chain?.symbol ?? "NIFTY"}</strong>
          <span className="metric-helper">{chain?.source ?? "Market API"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Current Price</span>
          <strong className="metric-value">{formatNumber(chain?.underlying_price)}</strong>
          <span className="metric-helper">{refreshLabel}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">ATM Strike</span>
          <strong className="metric-value">{chain?.atm_strike ?? "-"}</strong>
          <span className="metric-helper">Step {chain?.step ?? 50}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Expiry</span>
          <strong className="metric-value">{chain?.expiry ?? "-"}</strong>
          <span className="metric-helper">Synthetic/demo chain</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">PCR</span>
          <strong className="metric-value">{formatNumber(chain?.pcr)}</strong>
          <span className="metric-helper">Put/call open interest</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Max Pain</span>
          <strong className="metric-value">{chain?.max_pain ?? "-"}</strong>
          <span className="metric-helper">{chain?.greek_model ?? "Greeks"}</span>
        </div>
      </div>

      <div className="dashboard-section">
        <div className="section-header">
          <h2>NIFTY Option Chain</h2>
          <span>{loading ? "Loading" : refreshing ? "Refreshing" : "Ready"}</span>
        </div>
        <div className="table-wrap option-chain-wrap">
          <table className="table option-chain-table">
            <thead>
              <tr>
                <th>CE LTP</th>
                <th>CE OI</th>
                <th>CE Vol</th>
                <th>CE Delta</th>
                <th>Strike</th>
                <th>PE Delta</th>
                <th>PE Vol</th>
                <th>PE OI</th>
                <th>PE LTP</th>
              </tr>
            </thead>
            <tbody>
              {(chain?.rows ?? []).map((row: any) => (
                <tr key={row.strike} className={row.strike === chain?.atm_strike ? "option-atm-row" : ""}>
                  <td>{formatNumber(row.ce?.ltp)}</td>
                  <td>{formatNumber(row.ce?.oi)}</td>
                  <td>{formatNumber(row.ce?.volume)}</td>
                  <td>{formatNumber(row.ce?.greeks?.delta)}</td>
                  <td><strong>{row.strike}</strong></td>
                  <td>{formatNumber(row.pe?.greeks?.delta)}</td>
                  <td>{formatNumber(row.pe?.volume)}</td>
                  <td>{formatNumber(row.pe?.oi)}</td>
                  <td>{formatNumber(row.pe?.ltp)}</td>
                </tr>
              ))}
              {(!chain?.rows || chain.rows.length === 0) && (
                <tr>
                  <td colSpan={9}>Option chain data is not available yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
