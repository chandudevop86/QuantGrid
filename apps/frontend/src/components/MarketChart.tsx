import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Candle } from "./CandleChart";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import { useMarketSelection } from "../context/MarketSelectionContext";

type MarketChartProps = { support?: number; resistance?: number };

const WIDTH = 900;
const PRICE_HEIGHT = 230;
const VOLUME_TOP = 250;
const VOLUME_HEIGHT = 46;

export default function MarketChart({ support, resistance }: MarketChartProps) {
  const { symbol, label } = useMarketSelection();
  const decisionSupport = symbol === "NIFTY" ? support : undefined;
  const decisionResistance = symbol === "NIFTY" ? resistance : undefined;
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.candles(symbol, "5m");
      setCandles(Array.isArray(response?.candles) ? response.candles.slice(-48) : []);
    } catch (caught: any) {
      setError(caught?.message ?? "Candlestick data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => { void load(); }, [load]);

  const chart = useMemo(() => {
    if (!candles.length) return null;
    const allPrices = candles.flatMap((candle) => [candle.high, candle.low]);
    if (Number.isFinite(decisionSupport)) allPrices.push(Number(decisionSupport));
    if (Number.isFinite(decisionResistance)) allPrices.push(Number(decisionResistance));
    const min = Math.min(...allPrices);
    const max = Math.max(...allPrices);
    const range = Math.max(max - min, 1);
    const xStep = WIDTH / candles.length;
    const priceY = (price: number) => 12 + ((max - price) / range) * (PRICE_HEIGHT - 24);
    const maxVolume = Math.max(...candles.map((candle) => Number(candle.volume ?? 0)), 1);
    let cumulativePriceVolume = 0;
    let cumulativeVolume = 0;
    const vwap = candles.map((candle, index) => {
      const volume = Number(candle.volume ?? 0);
      cumulativePriceVolume += ((candle.high + candle.low + candle.close) / 3) * volume;
      cumulativeVolume += volume;
      const value = cumulativeVolume > 0 ? cumulativePriceVolume / cumulativeVolume : candle.close;
      return `${index * xStep + xStep / 2},${priceY(value)}`;
    }).join(" ");
    return { min, max, xStep, priceY, maxVolume, vwap };
  }, [candles, decisionSupport, decisionResistance]);

  return (
    <article className="qg-card qg-chart-card">
      <div className="qg-section-heading qg-chart-heading">
        <div><span>{label} · 5 minute</span><h2>Market chart</h2></div>
        <div className="qg-chart-legend" aria-label="Chart legend"><span className="price">Price</span><span className="vwap">VWAP</span><span className="support">Support</span><span className="resistance">Resistance</span></div>
      </div>
      {loading && <div className="qg-chart-loading" role="status">Loading chart…</div>}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && !chart && <EmptyState title="No candles available" message="The chart will appear when market data is available." />}
      {!loading && !error && chart && (
        <div className="qg-market-chart" role="img" aria-label={`${label} candlestick chart with volume, VWAP, support, and resistance`}>
          <svg viewBox={`0 0 ${WIDTH} 310`} preserveAspectRatio="none">
            {[0, 1, 2, 3].map((line) => <line key={line} className="qg-grid-line" x1="0" x2={WIDTH} y1={20 + line * 62} y2={20 + line * 62} />)}
            {Number.isFinite(decisionResistance) && <line className="qg-level-line qg-resistance-line" x1="0" x2={WIDTH} y1={chart.priceY(Number(decisionResistance))} y2={chart.priceY(Number(decisionResistance))} />}
            {Number.isFinite(decisionSupport) && <line className="qg-level-line qg-support-line" x1="0" x2={WIDTH} y1={chart.priceY(Number(decisionSupport))} y2={chart.priceY(Number(decisionSupport))} />}
            {candles.map((candle, index) => {
              const x = index * chart.xStep + chart.xStep / 2;
              const open = chart.priceY(candle.open);
              const close = chart.priceY(candle.close);
              const positive = candle.close >= candle.open;
              const volumeHeight = (Number(candle.volume ?? 0) / chart.maxVolume) * VOLUME_HEIGHT;
              return <g key={`${candle.timestamp}-${index}`} className={positive ? "qg-candle-up" : "qg-candle-down"}>
                <line x1={x} x2={x} y1={chart.priceY(candle.high)} y2={chart.priceY(candle.low)} />
                <rect x={x - Math.max(2, chart.xStep * .28)} y={Math.min(open, close)} width={Math.max(4, chart.xStep * .56)} height={Math.max(2, Math.abs(close - open))} rx="1" />
                <rect className="qg-volume-bar" x={x - Math.max(2, chart.xStep * .3)} y={VOLUME_TOP + VOLUME_HEIGHT - volumeHeight} width={Math.max(4, chart.xStep * .6)} height={volumeHeight} />
              </g>;
            })}
            <polyline className="qg-vwap-line" points={chart.vwap} />
          </svg>
          <div className="qg-chart-axis"><span>{chart.max.toFixed(0)}</span><span>{((chart.max + chart.min) / 2).toFixed(0)}</span><span>{chart.min.toFixed(0)}</span></div>
        </div>
      )}
    </article>
  );
}
