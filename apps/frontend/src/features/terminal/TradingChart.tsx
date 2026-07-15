import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type PriceLineOptions,
  type UTCTimestamp,
} from "lightweight-charts";
import { useCandlesQuery, type MarketCandle } from "./useCandlesQuery";
import type { Timeframe } from "./types";

type Props = { symbol: string; timeframe: Timeframe; support?: number; resistance?: number };
type ChartCandle = { time: UTCTimestamp; open: number; high: number; low: number; close: number };

function toTime(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

function normalized(candles: MarketCandle[]) {
  return candles
    .filter((item) => Number.isFinite(new Date(item.timestamp).getTime()))
    .map((item) => ({ ...item, time: toTime(item.timestamp) }))
    .sort((a, b) => Number(a.time) - Number(b.time));
}

function ema(candles: ReturnType<typeof normalized>, period = 20) {
  let previous = 0;
  const multiplier = 2 / (period + 1);
  return candles.map((item, index) => {
    previous = index === 0 ? item.close : (item.close - previous) * multiplier + previous;
    return { time: item.time, value: previous };
  });
}

function vwap(candles: ReturnType<typeof normalized>) {
  let cumulativeVolume = 0;
  let cumulativePV = 0;
  return candles.map((item) => {
    const volume = Number(item.volume ?? 0);
    cumulativeVolume += volume;
    cumulativePV += ((item.high + item.low + item.close) / 3) * volume;
    return { time: item.time, value: cumulativeVolume ? cumulativePV / cumulativeVolume : item.close };
  });
}


function priceLine(
  price: number,
  color: string,
  title: string
): PriceLineOptions {
  return {
    price,
    color,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,

    // Required in v5
    lineVisible: true,

    axisLabelVisible: true,
    axisLabelColor: color,
    axisLabelTextColor: "#ffffff",

    title,
  };
}
export default function TradingChart({ symbol, timeframe, support, resistance }: Props) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candlesSeries = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeries = useRef<ISeriesApi<"Histogram"> | null>(null);
  const emaSeries = useRef<ISeriesApi<"Line"> | null>(null);
  const vwapSeries = useRef<ISeriesApi<"Line"> | null>(null);
  const supportLine = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> | null>(null);
  const resistanceLine = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> | null>(null);
  const fittedMarket = useRef<string | null>(null);
  const { data = [], isLoading, isError } = useCandlesQuery(symbol, timeframe);
  const candles = useMemo(() => normalized(data), [data]);
  const marketKey = `${symbol}:${timeframe}`;

  useEffect(() => {
    if (!element.current) return;
    const instance = createChart(element.current, {
      layout: { background: { type: ColorType.Solid, color: "#080f18" }, textColor: "#8091a7", fontFamily: "Inter, system-ui, sans-serif", fontSize: 11 },
      grid: { vertLines: { color: "rgba(28,42,58,.62)" }, horzLines: { color: "rgba(28,42,58,.62)" } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#1c2a3a" },
      timeScale: { borderColor: "#1c2a3a", timeVisible: true, secondsVisible: false },
      handleScroll: true,
      handleScale: true,
    });
    const candle = instance.addSeries(CandlestickSeries, { upColor: "#26c69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26c69a", wickDownColor: "#ef5350" });
    const volume = instance.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", lastValueVisible: false, priceLineVisible: false });
    instance.priceScale("volume").applyOptions({ scaleMargins: { top: .78, bottom: 0 }, borderVisible: false });
    const average = instance.addSeries(LineSeries, { color: "#fbbf24", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
    const weighted = instance.addSeries(LineSeries, { color: "#22d3ee", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
    const resize = () => instance.applyOptions({ width: element.current?.clientWidth ?? 0, height: element.current?.clientHeight ?? 390 });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element.current);
    chart.current = instance;
    candlesSeries.current = candle;
    volumeSeries.current = volume;
    emaSeries.current = average;
    vwapSeries.current = weighted;
    return () => {
      observer.disconnect();
      instance.remove();
      chart.current = null;
      candlesSeries.current = null;
    };
  }, []);

  useEffect(() => {
    const series = candlesSeries.current;
    if (!series) return;
    if (supportLine.current) series.removePriceLine(supportLine.current);
    if (resistanceLine.current) series.removePriceLine(resistanceLine.current);
    supportLine.current = Number.isFinite(support) ? series.createPriceLine(priceLine(Number(support), "#34d399", "Support")) : null;
    resistanceLine.current = Number.isFinite(resistance) ? series.createPriceLine(priceLine(Number(resistance), "#fb7185", "Resistance")) : null;
  }, [support, resistance]);

  useEffect(() => {
    if (!candlesSeries.current) return;
    candlesSeries.current.setData(candles.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })) as ChartCandle[]);
    volumeSeries.current?.setData(candles.map((item) => ({ time: item.time, value: Number(item.volume ?? 0), color: item.close >= item.open ? "rgba(38,198,154,.45)" : "rgba(239,83,80,.45)" })));
    emaSeries.current?.setData(ema(candles));
    vwapSeries.current?.setData(vwap(candles));

    // Fit once per instrument/timeframe. Subsequent provider refreshes preserve pan and zoom.
    if (candles.length > 0 && fittedMarket.current !== marketKey) {
      chart.current?.timeScale().fitContent();
      fittedMarket.current = marketKey;
    }
  }, [candles, marketKey]);

  if (isError) return <div className="terminal-chart-state" role="alert">Chart data is unavailable. Try again when the configured market provider recovers.</div>;
  if (!isLoading && candles.length === 0) return <div className="terminal-chart-state" role="status">No verified candles are available for this instrument and timeframe.</div>;
  return <div className="terminal-lightweight-chart"><div ref={element} aria-label={`${symbol} ${timeframe} candlestick chart`} />{isLoading && <div className="terminal-chart-loading" role="status">Loading market chart…</div>}</div>;
}
