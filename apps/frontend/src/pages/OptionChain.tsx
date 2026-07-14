import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import CandleChart, { type Candle } from "../components/CandleChart";

const refreshMs = 60000;

type SelectedContract = {
  side: "CE" | "PE";
  strike: number;
  securityId: string;
  leg: any;
};

function formatNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "-";
}

function optionValue(option: any, ...keys: string[]) {
  for (const key of keys) {
    const value = option?.[key];
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function changeTone(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric !== 0 ? (numeric > 0 ? "is-positive" : "is-negative") : "";
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
  const [strikeWindow, setStrikeWindow] = useState(5);
  const [selectedContract, setSelectedContract] = useState<SelectedContract | null>(null);
  const [contractInterval, setContractInterval] = useState("1m");
  const [contractCandles, setContractCandles] = useState<Candle[]>([]);
  const [contractLoading, setContractLoading] = useState(false);
  const [contractError, setContractError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!selectedContract) return;
    setContractCandles([]);
    setContractLoading(true);
    setContractError(null);
    api.optionCandles(selectedContract.securityId, contractInterval, {
      symbol: String(chain?.symbol ?? "NIFTY"),
      strike: selectedContract.strike,
      side: selectedContract.side,
    })
      .then((payload: any) => setContractCandles(Array.isArray(payload?.candles) ? payload.candles : []))
      .catch((err: any) => setContractError(err?.response?.data?.detail ?? err?.message ?? "Live option candles are unavailable."))
      .finally(() => setContractLoading(false));
  }, [selectedContract, contractInterval]);

  useEffect(() => {
    if (!selectedContract) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedContract(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedContract]);

  const openContract = (side: "CE" | "PE", strike: number, leg: any) => {
    setContractInterval("1m");
    setSelectedContract({ side, strike, leg, securityId: String(optionValue(leg, "security_id", "securityId") ?? "") });
  };

  const refreshLabel = lastRefreshed
    ? `Updated ${lastRefreshed.toLocaleTimeString()}`
    : "Auto refresh every 60s";
  const usingSynthetic = String(chain?.source ?? "").includes("synthetic") || Boolean(chain?.synthetic);
  const isProviderBacked = ["dhan-option-chain", "yahoo-finance-options", "live", "live-nse-chain"].includes(String(chain?.source ?? ""));
  const providerWarning = String(chain?.warning ?? chain?.provider_warning ?? chain?.fallback_detail ?? "");
  const providerDiagnostics = chain?.provider_diagnostics;
  const likelyCauses = Array.isArray(providerDiagnostics?.likely_causes) ? providerDiagnostics.likely_causes : [];
  const suggestedActions = Array.isArray(providerDiagnostics?.suggested_actions) ? providerDiagnostics.suggested_actions : [];
  const rateLimited = providerDiagnostics?.code === "dhan_rate_limited";
  const retryAfterSeconds = Number(providerDiagnostics?.retry_after_seconds ?? 0);
  const chainUnavailable =
    chain?.source === "option-chain-unavailable"
    || chain?.provider_available === false
    || (
      !isProviderBacked
      && /token|rejected|unavailable|fresh token|option-chain provider/i.test(providerWarning)
    );
  const historyIsSynthetic = String(history?.source ?? "").includes("synthetic");
  const providerRows = usingSynthetic || chainUnavailable ? [] : chain?.rows ?? [];
  const atmStrike = Number(chain?.ATM ?? chain?.atm_strike ?? 0);
  const visibleRows = useMemo(() => {
    if (!providerRows.length || !atmStrike) return providerRows;
    const ordered = [...providerRows].sort((a: any, b: any) => Number(a?.strike ?? 0) - Number(b?.strike ?? 0));
    const atmIndex = ordered.reduce((best: number, row: any, index: number) => (
      Math.abs(Number(row?.strike ?? 0) - atmStrike) < Math.abs(Number(ordered[best]?.strike ?? 0) - atmStrike) ? index : best
    ), 0);
    return ordered.slice(Math.max(0, atmIndex - strikeWindow), atmIndex + strikeWindow + 1);
  }, [providerRows, atmStrike, strikeWindow]);
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
          disabled={loading || refreshing || rateLimited}
        >
          {refreshing ? "Refreshing" : rateLimited ? "Cooldown active" : "Refresh"}
        </button>
      </div>

      {loading && <div className="alert" role="status">Loading live option-chain data...</div>}
      {error && <div className="alert alert-warning" role="status">{error}</div>}
      {usingSynthetic && (
        <div className="alert alert-warning" role="status">
          Synthetic option-chain fallback was returned by the backend, so rows are hidden to avoid showing wrong live data.
        </div>
      )}
      {chainUnavailable && (
        <div className="alert alert-warning" role="status">
          Live option-chain rows are unavailable. Dhan login may be valid for profile, but option-chain access is not returning live rows.
        </div>
      )}
      {chain && !isProviderBacked && !usingSynthetic && !chainUnavailable && (
        <div className="alert alert-warning" role="status">
          Live Dhan option-chain data is not available; showing derived strike ladder only.
        </div>
      )}
      {chain?.warning && !error && <div className="alert alert-warning" role="status">{chain.warning}</div>}
      {rateLimited && (
        <div className="alert alert-warning" role="status">
          Dhan rate-limit protection is active. Manual refresh is disabled
          {retryAfterSeconds > 0 ? ` for approximately ${retryAfterSeconds} seconds` : " temporarily"}.
        </div>
      )}
      {chainUnavailable && providerDiagnostics && (
        <div className="dashboard-section">
          <div className="section-header">
            <h2>Dhan Diagnostics</h2>
            <span>{providerDiagnostics.code ?? "provider blocked"}</span>
          </div>
          <div className="metric-grid">
            <div className="metric-card">
              <span className="metric-label">Provider</span>
              <strong className="metric-value">{providerDiagnostics.provider ?? "dhan"}</strong>
              <span className="metric-helper">Status: {providerDiagnostics.status ?? "BLOCKED"}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Profile Login</span>
              <strong className="metric-value">{providerDiagnostics.profile_login_can_pass ? "Can Pass" : "Unknown"}</strong>
              <span className="metric-helper">Profile success does not guarantee Option Chain access</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Live Rows</span>
              <strong className="metric-value">{providerDiagnostics.live_rows_available ? "Available" : "Unavailable"}</strong>
              <span className="metric-helper">OI, PCR, max pain hidden until live rows return</span>
            </div>
          </div>
          <div className="alert alert-warning" role="status">
            <strong>Likely causes</strong>
            <ul>
              {(likelyCauses.length ? likelyCauses : ["Dhan Data API / Option Chain access is not available for this request."]).map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <strong>Next actions</strong>
            <ul>
              {(suggestedActions.length ? suggestedActions : ["Check Dhan entitlement, IP whitelist, client ID, and token."]).map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="option-chain-command" aria-label="Option chain summary">
        <div className="option-chain-symbol">
          <span className="metric-label">Underlying</span>
          <strong>{chain?.underlying ?? chain?.symbol ?? "NIFTY 50"}</strong>
          <span className="option-chain-spot">{usingSynthetic ? "-" : formatNumber(chain?.spot ?? chain?.underlying_price)}</span>
        </div>
        <div className="option-chain-expiry">
          <span className="metric-label">Expiry</span>
          <strong>{usingSynthetic || chainUnavailable ? "Unavailable" : chain?.expiry ?? "-"}</strong>
        </div>
        <dl className="option-chain-stats">
          <div><dt>ATM</dt><dd>{usingSynthetic || chainUnavailable ? "-" : chain?.ATM ?? chain?.atm_strike ?? "-"}</dd></div>
          <div><dt>PCR</dt><dd>{usingSynthetic || chainUnavailable ? "-" : formatNumber(chain?.pcr)}</dd></div>
          <div><dt>Max pain</dt><dd>{usingSynthetic || chainUnavailable ? "-" : formatNumber(chain?.max_pain)}</dd></div>
          <div><dt>Support</dt><dd>{usingSynthetic || chainUnavailable ? "-" : formatNumber(chain?.support)}</dd></div>
          <div><dt>Resistance</dt><dd>{usingSynthetic || chainUnavailable ? "-" : formatNumber(chain?.resistance)}</dd></div>
        </dl>
        <div className="option-chain-source"><span className={isProviderBacked ? "status-dot is-live" : "status-dot"} />{isProviderBacked ? "Live provider" : "Provider unavailable"}<small>{refreshLabel}</small></div>
      </div>

      <div className="dashboard-section option-chain-primary">
        <div className="section-header">
          <div><span className="metric-label">Live chain</span><h2>{chain?.source === "live-nse-chain" ? "NSE NIFTY Option Chain" : "NIFTY Option Chain"}</h2></div>
          <div className="option-chain-range" aria-label="Visible strikes">
            <span>Strikes</span>
            {[5, 10, 20].map((count) => <button type="button" className={strikeWindow === count ? "active" : ""} key={count} onClick={() => setStrikeWindow(count)}>ATM ±{count}</button>)}
          </div>
        </div>
        <div className="table-wrap option-chain-wrap">
          <table className="table option-chain-table" aria-label="NIFTY option chain calls and puts">
            <thead>
              <tr>
                <th className="option-side-heading" colSpan={5}>CALLS</th>
                <th className="option-strike-heading">STRIKE</th>
                <th className="option-side-heading" colSpan={5}>PUTS</th>
              </tr>
              <tr className="option-column-headings">
                <th>OI</th><th>Chg OI</th><th>Volume</th><th>IV</th><th>LTP</th>
                <th>Price</th>
                <th>LTP</th><th>IV</th><th>Volume</th><th>Chg OI</th><th>OI</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row: any) => {
                const strike = Number(row.strike);
                const callChangeOi = optionValue(row.ce, "change_oi", "chg_oi", "oi_change");
                const putChangeOi = optionValue(row.pe, "change_oi", "chg_oi", "oi_change");
                const callLtpChange = optionValue(row.ce, "change", "ltp_change", "price_change");
                const putLtpChange = optionValue(row.pe, "change", "ltp_change", "price_change");
                const isAtm = strike === atmStrike;
                return <tr key={row.strike} className={`${isAtm ? "option-atm-row" : ""}${strike < atmStrike ? " call-itm" : strike > atmStrike ? " put-itm" : ""}`}>
                  <td>{formatNumber(row.ce?.oi)}</td>
                  <td className={changeTone(callChangeOi)}>{formatNumber(callChangeOi)}</td>
                  <td>{formatNumber(row.ce?.volume)}</td>
                  <td>{formatNumber(optionValue(row.ce, "iv", "implied_volatility"))}</td>
                  <td><button type="button" className="option-contract-trigger" onClick={() => openContract("CE", strike, row.ce)} aria-label={`View NIFTY ${strike} CE candles`}><strong>{formatNumber(row.ce?.ltp)}</strong><small className={changeTone(callLtpChange)}>{formatNumber(callLtpChange)}</small></button></td>
                  <td className="option-strike-cell"><strong>{formatNumber(row.strike)}</strong>{isAtm && <span>ATM</span>}</td>
                  <td><button type="button" className="option-contract-trigger" onClick={() => openContract("PE", strike, row.pe)} aria-label={`View NIFTY ${strike} PE candles`}><strong>{formatNumber(row.pe?.ltp)}</strong><small className={changeTone(putLtpChange)}>{formatNumber(putLtpChange)}</small></button></td>
                  <td>{formatNumber(optionValue(row.pe, "iv", "implied_volatility"))}</td>
                  <td>{formatNumber(row.pe?.volume)}</td>
                  <td className={changeTone(putChangeOi)}>{formatNumber(putChangeOi)}</td>
                  <td>{formatNumber(row.pe?.oi)}</td>
                </tr>;
              })}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={11}>
                    {usingSynthetic
                      ? "Synthetic option-chain rows hidden. Configure Dhan/live provider for real chain data."
                      : chainUnavailable
                        ? "Live option-chain rows unavailable. Check Dhan Data API access, IP whitelist, client ID, and token."
                        : "Option chain data is not available yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <details className="dashboard-section option-chain-history">
        <summary><span>Historical chain</span><small>{history?.source ?? "History unavailable"}</small></summary>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Time</th><th>Underlying</th><th>ATM</th><th>PCR</th><th>Max Pain</th><th>Call OI</th><th>Put OI</th></tr></thead>
            <tbody>
              {visibleHistory.slice().reverse().map((row: any) => <tr key={row.timestamp}>
                <td>{row.timestamp ? new Date(row.timestamp).toLocaleTimeString() : "-"}</td><td>{formatNumber(row.underlying_price)}</td><td>{row.atm_strike ?? "-"}</td><td>{formatNumber(row.pcr)}</td><td>{row.max_pain ?? "-"}</td><td>{formatNumber(row.call_oi)}</td><td>{formatNumber(row.put_oi)}</td>
              </tr>)}
              {visibleHistory.length === 0 && <tr><td colSpan={7}>{historyIsSynthetic ? "Synthetic historical chain hidden." : "Historical chain data is not available yet."}</td></tr>}
            </tbody>
          </table>
        </div>
      </details>

      {selectedContract && (
        <div className="option-contract-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedContract(null); }}>
          <section className="option-contract-drawer" role="dialog" aria-modal="true" aria-labelledby="option-contract-title">
            <header>
              <div>
                <span className={`option-contract-side ${selectedContract.side.toLowerCase()}`}>{selectedContract.side === "CE" ? "CALL" : "PUT"}</span>
                <h2 id="option-contract-title">NIFTY {formatNumber(selectedContract.strike)} {selectedContract.side}</h2>
                <p>{chain?.expiry ?? "Current expiry"} · Dhan security ID {selectedContract.securityId || "unavailable"}</p>
              </div>
              <button type="button" className="option-contract-close" onClick={() => setSelectedContract(null)} aria-label="Close option candles">×</button>
            </header>

            <div className="option-contract-quote" aria-label="Option quote details">
              <div><span>LTP</span><strong>{formatNumber(selectedContract.leg?.ltp)}</strong></div>
              <div><span>OI</span><strong>{formatNumber(selectedContract.leg?.oi)}</strong></div>
              <div><span>Volume</span><strong>{formatNumber(selectedContract.leg?.volume)}</strong></div>
              <div><span>IV</span><strong>{formatNumber(optionValue(selectedContract.leg, "iv", "implied_volatility"))}</strong></div>
              <div><span>Bid</span><strong>{formatNumber(selectedContract.leg?.bid?.price)}</strong></div>
              <div><span>Ask</span><strong>{formatNumber(selectedContract.leg?.ask?.price)}</strong></div>
            </div>

            <div className="option-contract-chart-head">
              <div><strong>Contract candles</strong><small>Real NSE F&amp;O data supplied by Dhan</small></div>
              <div className="option-contract-intervals" aria-label="Contract candle interval">
                {["1m", "5m", "15m", "60m"].map((value) => <button type="button" key={value} className={contractInterval === value ? "active" : ""} onClick={() => setContractInterval(value)}>{value}</button>)}
              </div>
            </div>
            <div className="option-contract-chart">
              {contractLoading ? <div className="empty-state" role="status">Loading live option candles…</div> : contractError ? <div className="empty-state option-contract-error" role="alert">{contractError}</div> : <CandleChart candles={contractCandles} />}
            </div>
            <footer>Live provider data only. QuantGrid does not generate fallback candles for option contracts.</footer>
          </section>
        </div>
      )}
    </section>
  );
}
