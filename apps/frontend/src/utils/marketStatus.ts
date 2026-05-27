export type MarketStatusLabel = "LIVE" | "DELAYED" | "CLOSED" | "HOLIDAY";

export function getMarketStatusLabel(market: any): MarketStatusLabel {
  const state = String(market?.state ?? market?.market_status ?? market?.label ?? "").toUpperCase();
  const sessionState = String(market?.session_state ?? "").toLowerCase();

  if (state.includes("HOLIDAY")) return "HOLIDAY";
  if (state.includes("DELAYED")) return "DELAYED";
  if (state.includes("LIVE") || market?.valid_for_execution === true) return "LIVE";
  if (state.includes("CLOSED") || state.includes("WEEKEND") || sessionState === "closed") return "CLOSED";

  return "CLOSED";
}

export function getMarketStatusClass(label: MarketStatusLabel) {
  return `market-status-${label.toLowerCase()}`;
}
