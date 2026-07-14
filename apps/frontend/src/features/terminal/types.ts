export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT" | "SL";
export type TerminalTab = "positions" | "orders" | "history" | "journal" | "alerts" | "logs";
export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1D";

export interface Quote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  atr: number;
  trendScore: number;
  aiScore: number;
  signal: "Strong buy" | "Buy" | "Neutral" | "Sell";
  favorite?: boolean;
}

export interface OrderTicket {
  symbol: string;
  side: OrderSide;
  type: OrderType;
  quantity: number;
  price?: number;
  stopLoss: number;
  target: number;
  trailingStopPercent?: number;
  riskPercent: number;
  bracketOrder: boolean;
}

export interface TerminalPosition {
  id: string;
  symbol: string;
  product: string;
  side: OrderSide;
  quantity: number;
  averagePrice: number;
  lastPrice: number;
  pnl: number;
  pnlPercent: number;
  stopLoss: number;
  target: number;
}

export interface MarketStreamEvent { type: "quote" | "candle" | "status"; payload: Record<string, unknown>; }
