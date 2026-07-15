import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { getCurrentMode } from "../../mode";
import TradingChart from "./TradingChart";
import { useMarketStream } from "./useMarketStream";
import { useTerminalQuote } from "./useTerminalQuote";
import { useTerminalStore } from "./store";
import type { OrderTicket, TerminalTab, Timeframe } from "./types";

type WatchlistItem = { symbol: string; name: string; exchange: string };
type Activity = { id: string; time: string; event: string; detail: string; tone?: "positive" | "negative" };
type CopilotPayload = {
  confidence_score?: number;
  market_regime?: string;
  summary?: string;
  market_narrative?: string;
  invalidation_level?: number | null;
  invalidation_text?: string;
  signal_explanation?: { scenario?: string; reason?: string; why_now?: string };
};

const WATCHLIST: WatchlistItem[] = [
  { symbol: "NIFTY", name: "Nifty 50", exchange: "NSE" },
  { symbol: "BANKNIFTY", name: "Nifty Bank", exchange: "NSE" },
  { symbol: "RELIANCE", name: "Reliance Industries", exchange: "NSE" },
  { symbol: "HDFCBANK", name: "HDFC Bank", exchange: "NSE" },
];
const TABS: { id: TerminalTab; label: string }[] = [
  { id: "positions", label: "Positions" },
  { id: "orders", label: "Orders" },
  { id: "history", label: "Trade history" },
  { id: "journal", label: "Journal" },
  { id: "alerts", label: "Alerts" },
  { id: "logs", label: "Strategy logs" },
];
const FRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1D"];
const DRAWING_TOOLS = [["cursor", "⌖", "Cursor"], ["trendline", "╱", "Trendline"], ["horizontal", "━", "Horizontal line"], ["rectangle", "□", "Rectangle"], ["fib", "ƒ", "Fib retracement"], ["riskReward", "R", "Risk reward"]] as const;
const EMPTY_TICKET: OrderTicket = { symbol: "NIFTY", side: "BUY", type: "MARKET", quantity: 65, stopLoss: 0, target: 0, trailingStopPercent: 0, riskPercent: 1, bracketOrder: true };

function money(value: number | null | undefined) {
  return Number.isFinite(value) ? new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value)) : "—";
}

function rowsFrom(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload as Record<string, unknown>[];
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    for (const key of ["rows", "positions", "trades"]) {
      if (Array.isArray(record[key])) return record[key] as Record<string, unknown>[];
    }
  }
  return [];
}

function finite(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function valueOrBlank(value: number) {
  return value > 0 ? value : "";
}

export default function TerminalWorkspace() {
  const symbol = useTerminalStore((state) => state.symbol);
  const setSymbol = useTerminalStore((state) => state.setSymbol);
  const timeframe = useTerminalStore((state) => state.timeframe);
  const setTimeframe = useTerminalStore((state) => state.setTimeframe);
  const tab = useTerminalStore((state) => state.activeTab);
  const setTab = useTerminalStore((state) => state.setActiveTab);
  const activeDrawing = useTerminalStore((state) => state.activeDrawing);
  const setActiveDrawing = useTerminalStore((state) => state.setActiveDrawing);
  const [ticket, setTicket] = useState<OrderTicket>(EMPTY_TICKET);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  const socketStatus = useMarketStream();
  const quoteQuery = useTerminalQuote(symbol);
  const quote = quoteQuery.data;
  const livePrice = quote?.price ?? null;
  const filteredWatchlist = useMemo(
    () => WATCHLIST.filter((item) => `${item.symbol} ${item.name}`.toLowerCase().includes(query.trim().toLowerCase())),
    [query],
  );
  const positionsQuery = useQuery({
    queryKey: ["terminal", "positions", getCurrentMode()],
    queryFn: async () => rowsFrom(await api.openPositions()),
    refetchInterval: 15_000,
    staleTime: 5_000,
    retry: 1,
  });
  const copilotQuery = useQuery({
    queryKey: ["terminal", "copilot", symbol],
    queryFn: () => api.marketCopilot(symbol) as Promise<CopilotPayload>,
    staleTime: 30_000,
    retry: 1,
  });

  useEffect(() => {
    setTicket((current) => ({ ...current, symbol, price: livePrice ?? current.price }));
  }, [symbol, livePrice]);

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
        window.setTimeout(() => searchRef.current?.focus(), 0);
        return;
      }
      if ((event.target as HTMLElement | null)?.matches("input,select,textarea")) return;
      if (event.key.toLowerCase() === "b") setTicket((current) => ({ ...current, side: "BUY" }));
      if (event.key.toLowerCase() === "s") setTicket((current) => ({ ...current, side: "SELL" }));
      if (event.key.toLowerCase() === "p") setTab("positions");
      if (event.key === "Escape") setCommandOpen(false);
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [setTab]);

  const change = <K extends keyof OrderTicket>(key: K, value: OrderTicket[K]) => setTicket((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    const entryPrice = ticket.type === "MARKET" ? livePrice : finite(ticket.price);
    if (!entryPrice || entryPrice <= 0) {
      setNotice("A verified market price is required before an order can be submitted.");
      return;
    }
    if (ticket.quantity < 1) {
      setNotice("Quantity must be at least one unit.");
      return;
    }
    if (ticket.bracketOrder && (ticket.stopLoss <= 0 || ticket.target <= 0)) {
      setNotice("Enter both stop loss and target for a bracket order.");
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      await api.executeOrder({
        strategy_name: "terminal_manual",
        symbol: ticket.symbol,
        side: ticket.side,
        entry_price: entryPrice,
        stop_loss: ticket.stopLoss || undefined,
        target_price: ticket.target || undefined,
        trailing_stop_pct: ticket.trailingStopPercent || undefined,
        signal_time: new Date().toISOString(),
        metadata: { quantity: ticket.quantity, order_type: ticket.type, bracket_order: ticket.bracketOrder, source: "trading-terminal" },
      });
      const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setNotice(`${ticket.side} ${ticket.symbol} was sent to the ${getCurrentMode()} execution queue.`);
      setActivity((items) => [{ id: `order-${Date.now()}`, time, event: `${ticket.side} ${ticket.symbol} submitted`, detail: `${ticket.quantity} units · ${ticket.type} · ${getCurrentMode()} execution queue`, tone: ticket.side === "BUY" ? "positive" : "negative" }, ...items]);
      setTab("orders");
      void positionsQuery.refetch();
    } catch (error: any) {
      setNotice(error?.response?.data?.detail ?? "Order could not be submitted. Check the execution service.");
    } finally {
      setSubmitting(false);
    }
  };

  const changePercent = quote?.changePercent;
  const priceClass = changePercent == null ? "" : changePercent >= 0 ? "positive" : "negative";

  return <section className="terminal" aria-label="QuantGrid trading terminal">
    <header className="terminal-commandbar">
      <div>
        <span className="terminal-kicker">Trading terminal · {quote?.provider?.toUpperCase() ?? "market data"}</span>
        <strong>{WATCHLIST.find((item) => item.symbol === symbol)?.name ?? symbol} <em>{money(livePrice)}</em></strong>
        {changePercent != null && <span className={priceClass}>{changePercent >= 0 ? "+" : ""}{changePercent.toFixed(2)}%</span>}
      </div>
      <div>
        <span className={`stream-state ${socketStatus}`}>{socketStatus === "connected" ? "Workspace connected" : socketStatus === "connecting" ? "Connecting workspace" : "Workspace reconnecting"}</span>
        <button className="terminal-icon-button" type="button" aria-label="Open instrument command palette" onClick={() => setCommandOpen(true)}>⌘ K</button>
      </div>
    </header>

    <section className="terminal-market-strip" aria-label="Terminal data status">
      <span><small>Data source</small><b>{quote?.provider ?? (quoteQuery.isLoading ? "Loading" : "Unavailable")}</b></span>
      <span><small>Last update</small><b>{quote?.timestamp ? new Date(quote.timestamp).toLocaleTimeString() : "—"}</b></span>
      <span><small>Chart interval</small><b>{timeframe}</b></span>
      <span><small>Execution mode</small><b>{getCurrentMode()}</b></span>
      <span><small>Open positions</small><b>{positionsQuery.data?.length ?? "—"}</b></span>
    </section>

    {quote?.warning && <p className="terminal-data-warning" role="status">{quote.warning}</p>}
    {quoteQuery.isError && <p className="terminal-data-warning is-error" role="alert">Live price is unavailable. The order ticket remains disabled until a verified price is returned.</p>}

    {commandOpen && <CommandPalette items={filteredWatchlist} inputRef={searchRef} query={query} setQuery={setQuery} onSelect={(nextSymbol) => { setSymbol(nextSymbol); setQuery(""); setCommandOpen(false); }} onClose={() => setCommandOpen(false)} />}

    <div className="terminal-grid">
      <aside className="terminal-left">
        <Watchlist items={filteredWatchlist} symbol={symbol} price={livePrice} onSelect={setSymbol} query={query} setQuery={setQuery} />
        <MarketPanels />
      </aside>
      <main className="terminal-center">
        <section className="terminal-panel chart-shell">
          <div className="chart-toolbar">
            <div className="timeframe-group" role="group" aria-label="Chart interval">
              {FRAMES.map((item) => <button type="button" aria-pressed={item === timeframe} className={item === timeframe ? "active" : ""} onClick={() => setTimeframe(item)} key={item}>{item}</button>)}
            </div>
            <div className="chart-actions"><button type="button" title="EMA 20, VWAP, volume, support and resistance are enabled">Indicators</button><button type="button" title="Select a supported drawing tool from the rail">Drawings</button><button type="button" onClick={() => void quoteQuery.refetch()}>Refresh</button></div>
          </div>
          <div className="chart-annotations"><span>EMA 20</span><span>VWAP</span><span>Volume</span><span>Support / resistance</span></div>
          <TradingChart symbol={symbol} timeframe={timeframe} />
          <div className="drawing-rail" role="toolbar" aria-label="Chart drawing tools">
            {DRAWING_TOOLS.map(([tool, icon, label]) => <button className={activeDrawing === tool ? "active" : ""} type="button" title={label} aria-label={label} aria-pressed={activeDrawing === tool} onClick={() => setActiveDrawing(tool)} key={tool}>{icon}</button>)}
          </div>
        </section>
        <AiPanel payload={copilotQuery.data} isLoading={copilotQuery.isLoading} isError={copilotQuery.isError} />
      </main>
      <aside className="terminal-right">
        <OrderPanel price={livePrice} ticket={ticket} change={change} submit={submit} submitting={submitting} notice={notice} />
        <PositionCalculator price={livePrice} ticket={ticket} />
      </aside>
    </div>

    <section className="terminal-panel terminal-bottom">
      <div className="bottom-tabs" role="tablist" aria-label="Trading records">
        {TABS.map((item) => <button type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)} key={item.id}>{item.label}{item.id === "positions" && (positionsQuery.data?.length ?? 0) > 0 && <span>{positionsQuery.data?.length}</span>}</button>)}
      </div>
      <TerminalDock tab={tab} positions={positionsQuery.data ?? []} positionsLoading={positionsQuery.isLoading} positionsError={positionsQuery.isError} activity={activity} />
    </section>
  </section>;
}

function CommandPalette({ items, inputRef, query, setQuery, onSelect, onClose }: { items: WatchlistItem[]; inputRef: React.RefObject<HTMLInputElement>; query: string; setQuery: (value: string) => void; onSelect: (symbol: string) => void; onClose: () => void }) {
  return <div className="terminal-command-palette" role="dialog" aria-modal="true" aria-label="Instrument command palette"><button className="terminal-command-backdrop" aria-label="Close command palette" onClick={onClose} /><div className="terminal-command-dialog"><span className="terminal-kicker">Jump to instrument</span><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search NIFTY, BANKNIFTY, RELIANCE…" aria-label="Search instruments" />{items.map((item) => <button key={item.symbol} type="button" onClick={() => onSelect(item.symbol)}><span><b>{item.symbol}</b><small>{item.name}</small></span><strong>{item.exchange}</strong></button>)}{!items.length && <p className="terminal-empty-message">No instruments match your search.</p>}</div></div>;
}

function Watchlist({ items, symbol, price, onSelect, query, setQuery }: { items: WatchlistItem[]; symbol: string; price: number | null; onSelect: (symbol: string) => void; query: string; setQuery: (value: string) => void }) {
  return <section className="terminal-panel watchlist-panel"><div className="panel-title"><h2>Watchlist</h2><span>Live on select</span></div><input className="terminal-search" aria-label="Search watchlist" placeholder="Search instruments" value={query} onChange={(event) => setQuery(event.target.value)} /><div className="watchlist-header"><span>Instrument</span><span>Last</span><span>Feed</span></div>{items.map((item) => <button type="button" className={`watch-row ${item.symbol === symbol ? "selected" : ""}`} onClick={() => onSelect(item.symbol)} key={item.symbol}><span><b>{item.symbol}</b><small>{item.name}</small></span><strong>{item.symbol === symbol ? money(price) : "—"}</strong><i>{item.symbol === symbol ? "Loaded" : "Select"}</i></button>)}{!items.length && <p className="terminal-empty-message">No instruments match your search.</p>}</section>;
}

function MarketPanels() {
  return <><section className="terminal-panel compact-panel"><div className="panel-title"><h2>Market overview</h2><span>Configured feed</span></div><div className="market-mini"><span>Price <b>On selection</b></span><span>Candles <b>Verified API</b></span><span>Orders <b>Paper guarded</b></span></div></section><section className="terminal-panel compact-panel"><div className="panel-title"><h2>Saved screeners</h2><Link to="/ai-scanner">Open</Link></div><p className="terminal-panel-copy">Run your entitled scanner from the dedicated workspace. Results are not duplicated in the order flow.</p></section></>;
}

function AiPanel({ payload, isLoading, isError }: { payload: CopilotPayload | undefined; isLoading: boolean; isError: boolean }) {
  const explanation = payload?.signal_explanation;
  return <section className="terminal-panel ai-panel"><div className="panel-title"><div><span className="terminal-kicker">QuantGrid AI</span><h2>Trade intelligence</h2></div><span className="ai-score">{isLoading ? "…" : payload?.confidence_score ?? "—"}<small>/100</small></span></div>{isError ? <p className="terminal-panel-copy" role="status">AI context is unavailable for this account or market state. It never blocks risk controls.</p> : <><div className="ai-metrics"><span><small>Regime</small><b>{payload?.market_regime ?? "—"}</b></span><span><small>Scenario</small><b>{explanation?.scenario ?? "—"}</b></span><span><small>Invalidation</small><b>{money(payload?.invalidation_level)}</b></span><span><small>Why now</small><b>{explanation?.why_now ?? "—"}</b></span></div><p>{payload?.summary ?? payload?.market_narrative ?? "Waiting for the configured AI market context."}</p></>}</section>;
}

function OrderPanel({ price, ticket, change, submit, submitting, notice }: { price: number | null; ticket: OrderTicket; change: <K extends keyof OrderTicket>(key: K, value: OrderTicket[K]) => void; submit: () => Promise<void>; submitting: boolean; notice: string | null }) {
  const risk = price && ticket.stopLoss > 0 ? Math.abs(price - ticket.stopLoss) * ticket.quantity : null;
  const reward = price && ticket.stopLoss > 0 && ticket.target > 0 ? Math.abs(ticket.target - price) / Math.max(Math.abs(price - ticket.stopLoss), 1) : null;
  return <section className="terminal-panel order-panel"><div className="panel-title"><h2>Order entry</h2><span className="paper-badge">{getCurrentMode()}</span></div><div className="side-toggle"><button type="button" className={ticket.side === "BUY" ? "buy active" : "buy"} onClick={() => change("side", "BUY")}>Buy <kbd>B</kbd></button><button type="button" className={ticket.side === "SELL" ? "sell active" : "sell"} onClick={() => change("side", "SELL")}>Sell <kbd>S</kbd></button></div><div className="order-types">{(["MARKET", "LIMIT", "SL"] as const).map((type) => <button type="button" className={ticket.type === type ? "active" : ""} onClick={() => change("type", type)} key={type}>{type}</button>)}</div><label>Quantity<input type="number" min="1" value={ticket.quantity} onChange={(event) => change("quantity", Math.max(1, Number(event.target.value)))} /></label>{ticket.type !== "MARKET" && <label>Limit price<input type="number" min="0" value={ticket.price ?? ""} onChange={(event) => change("price", Number(event.target.value))} /></label>}<div className="ticket-grid"><label>Stop loss<input type="number" min="0" value={valueOrBlank(ticket.stopLoss)} onChange={(event) => change("stopLoss", Number(event.target.value))} /></label><label>Target<input type="number" min="0" value={valueOrBlank(ticket.target)} onChange={(event) => change("target", Number(event.target.value))} /></label><label>Trail %<input type="number" min="0" step=".1" value={valueOrBlank(ticket.trailingStopPercent ?? 0)} onChange={(event) => change("trailingStopPercent", Number(event.target.value))} /></label><label>Risk %<input type="number" min="0" step=".25" value={ticket.riskPercent} onChange={(event) => change("riskPercent", Number(event.target.value))} /></label></div><label className="checkline"><input type="checkbox" checked={ticket.bracketOrder} onChange={(event) => change("bracketOrder", event.target.checked)} /> Bracket order (SL + target)</label><div className="order-summary-grid"><span><small>Reference LTP</small><b>{money(price)}</b></span><span><small>Risk</small><b>{risk == null ? "—" : `₹${money(risk)}`}</b></span><span><small>R:R</small><b>{reward == null ? "—" : `1:${reward.toFixed(1)}`}</b></span></div><button type="button" className={`place-order ${ticket.side.toLowerCase()}`} disabled={submitting || price == null} onClick={() => void submit()}>{submitting ? "Submitting…" : price == null ? "Waiting for verified price" : `${ticket.side === "BUY" ? "Buy" : "Sell"} ${ticket.symbol}`}</button>{notice && <p role="status" className="order-notice">{notice}</p>}</section>;
}

function PositionCalculator({ price, ticket }: { price: number | null; ticket: OrderTicket }) {
  const potentialLoss = price && ticket.stopLoss > 0 ? Math.abs(price - ticket.stopLoss) * ticket.quantity : null;
  return <section className="terminal-panel calculator-panel"><div className="panel-title"><h2>Position size</h2><span>Manual ticket</span></div><p>Quantity stays under your server-side risk gate.</p><strong>{ticket.quantity} <small>units</small></strong><span>{potentialLoss == null ? "Enter a verified price and stop loss to calculate risk." : `Estimated loss ₹${money(potentialLoss)}`}</span></section>;
}

function TerminalDock({ tab, positions, positionsLoading, positionsError, activity }: { tab: TerminalTab; positions: Record<string, unknown>[]; positionsLoading: boolean; positionsError: boolean; activity: Activity[] }) {
  if (tab === "positions") return <PositionTable rows={positions} loading={positionsLoading} error={positionsError} />;
  if (tab === "orders") return activity.length ? <div className="terminal-activity-list">{activity.map((item) => <ActivityRow item={item} key={item.id} />)}</div> : <EmptyDock title="No orders in this terminal session" detail="Submitted orders appear here immediately. Use Positions to see confirmed open exposure." />;
  if (tab === "history") return <DockLink title="Review completed trades" detail="Trade history remains in the dedicated record, with filters and export controls." to="/paper-trades" label="Open positions & history" />;
  if (tab === "journal") return <DockLink title="Trading journal" detail="Add notes against completed trades from the journal workspace." to="/trade-journal" label="Open journal" />;
  if (tab === "alerts") return <EmptyDock title="No terminal alerts loaded" detail="System and trade alerts remain available in the application header." />;
  return <DockLink title="Strategy logs" detail="Use the execution workspace for server-provided strategy activity." to="/execution" label="Open execution" />;
}

function PositionTable({ rows, loading, error }: { rows: Record<string, unknown>[]; loading: boolean; error: boolean }) {
  if (loading) return <EmptyDock title="Loading open positions" detail="Fetching the active account from the execution API." />;
  if (error) return <EmptyDock title="Position data is unavailable" detail="Use the Positions page to retry or inspect the execution service." />;
  if (!rows.length) return <EmptyDock title="No open positions" detail="Open exposure from the active account appears here. No simulated positions are shown." />;
  return <div className="terminal-table-wrap"><table><thead><tr><th>Instrument</th><th>Side</th><th>Quantity</th><th>Average</th><th>LTP</th><th>SL / Target</th><th>P&amp;L</th><th /></tr></thead><tbody>{rows.map((row) => { const pnl = finite(row.open_pnl ?? row.pnl) ?? 0; const entry = finite(row.entry_price ?? row.entry); const ltp = finite(row.current_price ?? row.ltp); const quantity = finite(row.quantity); const percent = entry && quantity ? (pnl / Math.abs(entry * quantity)) * 100 : null; return <tr key={String(row.id ?? row.broker_order_id ?? `${row.symbol}-${row.opened_at}`)}><td><b>{String(row.symbol ?? "—")}</b><small>{String(row.product ?? row.product_type ?? "Position")}</small></td><td>{String(row.side ?? "—")}</td><td>{quantity ?? "—"}</td><td>{money(entry)}</td><td>{money(ltp)}</td><td>{money(finite(row.stop_loss))} / {money(finite(row.target))}</td><td className={pnl >= 0 ? "positive" : "negative"}><b>₹{money(pnl)}</b><small>{percent == null ? "—" : `${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%`}</small></td><td><Link to="/paper-trades">Manage</Link></td></tr>; })}</tbody></table></div>;
}

function ActivityRow({ item }: { item: Activity }) {
  return <article className="terminal-activity-row"><time>{item.time}</time><span className={`activity-pip ${item.tone ?? ""}`} /><div><b>{item.event}</b><small>{item.detail}</small></div><Link to="/paper-trades">View</Link></article>;
}

function EmptyDock({ title, detail }: { title: string; detail: string }) {
  return <div className="tab-empty"><strong>{title}</strong><span>{detail}</span></div>;
}

function DockLink({ title, detail, to, label }: { title: string; detail: string; to: string; label: string }) {
  return <div className="tab-empty"><strong>{title}</strong><span>{detail}</span><Link className="terminal-dock-link" to={to}>{label}</Link></div>;
}
