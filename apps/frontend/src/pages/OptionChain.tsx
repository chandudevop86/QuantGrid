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

function demoOptionChain(symbol = "NIFTY") {
  const underlying = 22500;
  const step = 50;
  const atm = 22500;
  const rows = Array.from({ length: 11 }, (_, index) => {
    const strike = atm + (index - 5) * step;
    const distance = Math.abs(strike - underlying);
    const timeValue = Math.max(12, 95 * Math.exp(-distance / (step * 4)));
    const ceOi = Math.round(90000 + Math.max(index - 5, 0) * 17500 + distance * 80);
    const peOi = Math.round(90000 + Math.max(5 - index, 0) * 17500 + distance * 80);
    const deltaShift = Math.max(-1, Math.min(1, (atm - strike) / (step * 4)));

    return {
      strike,
      ce: {
        ltp: Number((Math.max(underlying - strike, 0) + timeValue).toFixed(2)),
        oi: ceOi,
        volume: Math.round(ceOi * 0.18),
        greeks: { delta: Number((0.5 + deltaShift / 2).toFixed(2)) },
      },
      pe: {
        ltp: Number((Math.max(strike - underlying, 0) + timeValue).toFixed(2)),
        oi: peOi,
        volume: Math.round(peOi * 0.18),
        greeks: { delta: Number((-0.5 + deltaShift / 2).toFixed(2)) },
      },
    };
  });

  return enrichOptionChain({
    symbol,
    underlying_price: underlying,
    atm_strike: atm,
    step,
    expiry: "Demo",
    source: "offline-demo-chain",
    warning: "Backend is offline; showing demo option-chain data.",
    rows,
  });
}

function demoHistoricalChain(symbol = "NIFTY") {
  const now = Date.now();
  const snapshots = Array.from({ length: 12 }, (_, index) => {
    const age = 11 - index;
    const underlying = 22500 + ((index % 5) - 2) * 18 - age * 1.75;
    const atm = Math.round(underlying / 50) * 50;
    const callOi = 950000 + index * 7200 + Math.max(underlying - atm, 0) * 120;
    const putOi = 940000 + (12 - index) * 6500 + Math.max(atm - underlying, 0) * 120;
    const pcr = callOi > 0 ? putOi / callOi : 0;

    return {
      timestamp: new Date(now - age * 5 * 60 * 1000).toISOString(),
      underlying_price: Number(underlying.toFixed(2)),
      atm_strike: atm,
      pcr: Number(pcr.toFixed(3)),
      max_pain: atm + (pcr > 1.05 ? 50 : pcr < 0.95 ? -50 : 0),
      call_oi: Math.round(callOi),
      put_oi: Math.round(putOi),
    };
  });

  return {
    module: "historical_option_chain",
    symbol,
    source: "offline-synthetic-history",
    interval: "5m",
    snapshots,
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

    const chainRequest = api
      .optionChainEngine("NIFTY")
      .catch((err: any) => {
        if (err?.response?.status === 404) {
          return api.optionChain("NIFTY").then(enrichOptionChain);
        }
        throw err;
      });
    const historyRequest = api
      .historicalOptionChain("NIFTY")
      .catch(() => demoHistoricalChain("NIFTY"));

    return Promise.all([chainRequest, historyRequest])
      .then(([data, historicalData]) => {
        setChain(enrichOptionChain(data));
        setHistory(historicalData);
        setLastRefreshed(new Date());
      })
      .catch((err: any) => {
        if (err?.message === "Network Error" || !err?.response) {
          setChain(demoOptionChain("NIFTY"));
          setHistory(demoHistoricalChain("NIFTY"));
          setError(null);
          setLastRefreshed(new Date());
          return;
        }
        setError(err?.response?.data?.detail ?? err?.message ?? "Failed to load option chain.");
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
              {(history?.snapshots ?? []).slice().reverse().map((row: any) => (
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
              {(!history?.snapshots || history.snapshots.length === 0) && (
                <tr>
                  <td colSpan={7}>Historical chain data is not available yet.</td>
                </tr>
              )}
            </tbody>
          </table>
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
