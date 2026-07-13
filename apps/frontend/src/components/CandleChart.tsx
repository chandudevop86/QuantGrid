export type Candle = {
  symbol?: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type CandleChartProps = {
  candles: Candle[];
};

export default function CandleChart({ candles }: CandleChartProps) {
  if (candles.length === 0) {
    return (
      <div className="empty-state">
        No candles available yet.
      </div>
    );
  }

  const prices = candles.flatMap((candle) => [candle.high, candle.low]);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = Math.max(maxPrice - minPrice, 1);

  const yFor = (price: number) => 6 + ((maxPrice - price) / priceRange) * 82;

  return (
    <div className="candle-chart" role="img" aria-label="NIFTY candlestick chart">
      <div className="price-axis">
        <span>{maxPrice.toFixed(2)}</span>
        <span>{((maxPrice + minPrice) / 2).toFixed(2)}</span>
        <span>{minPrice.toFixed(2)}</span>
      </div>

      <div className="candle-plot">
        {candles.map((candle) => {
          const isUp = candle.close >= candle.open;
          const highY = yFor(candle.high);
          const lowY = yFor(candle.low);
          const openY = yFor(candle.open);
          const closeY = yFor(candle.close);
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(openY - closeY), 4);
          const time = new Date(candle.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          });

          return (
            <div className="candle-column" key={candle.timestamp} title={`${time} O ${candle.open} H ${candle.high} L ${candle.low} C ${candle.close}`}>
              <div
                className="candle-wick"
                style={{
                  top: `${highY}%`,
                  height: `${Math.max(lowY - highY, 0.8)}%`,
                }}
              />
              <div
                className={`candle-body${isUp ? " up" : " down"}`}
                style={{
                  top: `${bodyTop}%`,
                  height: `${Math.max(bodyHeight, 1.6)}%`,
                }}
              />
              <span>{time}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
