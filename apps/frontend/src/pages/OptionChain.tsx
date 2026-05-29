import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const refreshMs = 15000;

function formatNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "-";
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
      .optionChain("NIFTY")
      .then((data) => {
        setChain(data);
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
          <span className="metric-helper">Nearest available chain</span>
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
                <th>Strike</th>
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
                  <td><strong>{row.strike}</strong></td>
                  <td>{formatNumber(row.pe?.volume)}</td>
                  <td>{formatNumber(row.pe?.oi)}</td>
                  <td>{formatNumber(row.pe?.ltp)}</td>
                </tr>
              ))}
              {(!chain?.rows || chain.rows.length === 0) && (
                <tr>
                  <td colSpan={7}>Option chain data is not available yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
