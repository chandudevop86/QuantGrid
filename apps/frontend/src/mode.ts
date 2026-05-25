export type TradingMode = "paper" | "live";

export const modes: TradingMode[] = ["paper", "live"];

export const modeLabels: Record<TradingMode, string> = {
  paper: "Paper",
  live: "Live",
};

export function getCurrentMode(): TradingMode {
  const storedMode =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_mode");
  const configuredMode = import.meta.env.VITE_DEFAULT_MODE;
  const mode = storedMode ?? configuredMode ?? "paper";

  return modes.includes(mode as TradingMode) ? (mode as TradingMode) : "paper";
}

export function setCurrentMode(mode: TradingMode) {
  window.localStorage.setItem("quantgrid_mode", mode);
  window.dispatchEvent(new CustomEvent("quantgrid-mode-change", { detail: mode }));
}
