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
  return {
    ...data,
    pcr: data?.pcr ?? (totalCallOi > 0 ? Number((totalPutOi / totalCallOi).toFixed(3)) : undefined),
    max_pain: data?.max_pain ?? maxPain,
    greek_model: data?.greek_model ?? (rows.some((row: any) => row?.ce?.greeks || row?.pe?.greeks) ? "provider greeks" : undefined),
    source: data?.source ?? "market-option-chain",
    rows,
  };
}

export default function OptionChain() {
  const [chain, setChain] = useState<any>(null);
  const [history, setHistory] = useState<any>(null);
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

    const chainRequest = api.optionChain("NIFTY");
    const historyRequest = api
      .historicalOptionChain("NIFTY")
      .catch(() => null);

    return Promise.all([chainRequest, historyRequest])
      .then(([data, historicalData]) => {
        setChain(enrichOptionChain(data));
        setHistory(historicalData);
        setLastRefreshed(new Date());
      })
      .catch((err: any) => {
        setChain(null);
        setHistory(null);
        setLastRefreshed(new Date());
        setError(
          err?.message === "Network Error" || !err?.response
            ? "Option chain API is unavailable. No live option-chain data is being shown."
            : err?.response?.data?.detail ?? err?.message ?? "Failed to load live option chain."
        );
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
  const usingSynthetic = String(chain?.source ?? "").includes("synthetic") || Boolean(chain?.synthetic);
  const isProviderBacked = ["dhan-option-chain", "yahoo-finance-options", "live", "live-nse-chain"].includes(String(chain?.source ?? ""));
  const historyIsSynthetic = String(history?.source ?? "").includes("synthetic");
  const visibleRows = usingSynthetic ? [] : chain?.rows ?? [];
  const visibleHistory = historyIsSynthetic ? [] : history?.snapshots ?? [];

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Option Chain</h1>
          <p>Live broker option-chain data, real OI, real PCR, and chain-derived signals.</p>
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

      {loading && <div className="alert" role="status">Loading live option-chain data...</div>}
      {error && <div className="alert alert-warning" role="status">{error}</div>}
      {usingSynthetic && (
        <div className="alert alert-warning" role="status">
          Synthetic option-chain fallback was returned by the backend, so rows are hidden to avoid showing wrong live data.
        </div>
      )}
      {chain && !isProviderBacked && !usingSynthetic && (
        <div className="alert alert-warning" role="status">
          Live Dhan option-chain data is not available; showing derived strike ladder only.
        </div>
      )}
      {chain?.warning && !error && <div className="alert alert-warning" role="status">{chain.warning}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Underlying</span>
          <strong className="metric-value">{chain?.underlying ?? chain?.symbol ?? "NIFTY"}</strong>
          <span className="metric-helper">Source: {chain?.source ?? "synthetic"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Current Price</span>
          <strong className="metric-value">{usingSynthetic ? "-" : formatNumber(chain?.spot ?? chain?.underlying_price)}</strong>
          <span className="metric-helper">{refreshLabel}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">ATM Strike</span>
          <strong className="metric-value">{usingSynthetic ? "-" : chain?.ATM ?? chain?.atm_strike ?? "-"}</strong>
          <span className="metric-helper">Step {chain?.step ?? 50}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Expiry</span>
          <strong className="metric-value">{chain?.expiry ?? "Demo"}</strong>
          <span className="metric-helper">{isProviderBacked ? "Provider chain" : chain ? "Fallback ladder" : "No chain loaded"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">PCR</span>
          <strong className="metric-value">{usingSynthetic ? "-" : formatNumber(chain?.pcr)}</strong>
          <span className="metric-helper">Put/call open interest</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Max Pain</span>
          <strong className="metric-value">{usingSynthetic ? "-" : chain?.max_pain ?? "-"}</strong>
          <span className="metric-helper">{chain?.greek_model ?? "Greeks unavailable"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Support</span>
          <strong className="metric-value">{usingSynthetic ? "-" : chain?.support ?? "-"}</strong>
          <span className="metric-helper">Highest put OI below ATM</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Resistance</span>
          <strong className="metric-value">{usingSynthetic ? "-" : chain?.resistance ?? "-"}</strong>
          <span className="metric-helper">Highest call OI above ATM</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Real Signal</span>
          <strong className="metric-value">{usingSynthetic ? "NO_LIVE_DATA" : chain?.signal ?? chain?.signals?.bias ?? "NO_TRADE"}</strong>
          <span className="metric-helper">{chain?.signals?.reason ?? "PCR / OI / max pain"}</span>
        </div>
      </div>

      <div className="dashboard-section">
        <div className="section-header">
          <h2>Historical Chain</h2>
          <span>{history?.source ?? "Synthetic history"}</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Underlying</th>
                <th>ATM</th>
                <th>PCR</th>
                <th>Max Pain</th>
                <th>Call OI</th>
                <th>Put OI</th>
              </tr>
            </thead>
            <tbody>
              {visibleHistory.slice().reverse().map((row: any) => (
                <tr key={row.timestamp}>
                  <td>{row.timestamp ? new Date(row.timestamp).toLocaleTimeString() : "-"}</td>
                  <td>{formatNumber(row.underlying_price)}</td>
                  <td>{row.atm_strike ?? "-"}</td>
                  <td>{formatNumber(row.pcr)}</td>
                  <td>{row.max_pain ?? "-"}</td>
                  <td>{formatNumber(row.call_oi)}</td>
                  <td>{formatNumber(row.put_oi)}</td>
                </tr>
              ))}
              {visibleHistory.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    {historyIsSynthetic ? "Synthetic historical chain hidden." : "Historical chain data is not available yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="dashboard-section">
        <div className="section-header">
          <h2>{chain?.source === "live-nse-chain" ? "Live NSE Chain" : "NIFTY Option Chain"}</h2>
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
              {visibleRows.map((row: any) => (
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
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={9}>
                    {usingSynthetic ? "Synthetic option-chain rows hidden. Configure Dhan/live provider for real chain data." : "Option chain data is not available yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
