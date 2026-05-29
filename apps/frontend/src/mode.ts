export type TradingMode = "paper" | "live";
export type UiMode = "trader" | "developer";

export const modes: TradingMode[] = ["paper", "live"];
export const uiModes: UiMode[] = ["trader", "developer"];

export const modeLabels: Record<TradingMode, string> = {
  paper: "Paper",
  live: "Live",
};

export const uiModeLabels: Record<UiMode, string> = {
  trader: "Trader",
  developer: "Developer",
};

export function getCurrentMode(): TradingMode {
  if (isInsecureRemoteHttp()) return "paper";

  const storedMode =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_mode");
  const configuredMode = import.meta.env.VITE_DEFAULT_MODE;
  const mode = storedMode ?? configuredMode ?? "paper";

  return modes.includes(mode as TradingMode) ? (mode as TradingMode) : "paper";
}

export function setCurrentMode(mode: TradingMode) {
  if (mode === "live" && isInsecureRemoteHttp()) {
    window.localStorage.setItem("quantgrid_mode", "paper");
    window.dispatchEvent(new CustomEvent("quantgrid-mode-change", { detail: "paper" }));
    return;
  }
  window.localStorage.setItem("quantgrid_mode", mode);
  window.dispatchEvent(new CustomEvent("quantgrid-mode-change", { detail: mode }));
}

export function isLocalhostHost(hostname: string) {
  return ["localhost", "127.0.0.1", "::1"].includes(hostname) || hostname.endsWith(".localhost");
}

export function isInsecureRemoteHttp() {
  if (typeof window === "undefined") return false;
  return window.location.protocol === "http:" && !isLocalhostHost(window.location.hostname);
}

export function getCurrentUiMode(): UiMode {
  const storedMode =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_ui_mode");
  return uiModes.includes(storedMode as UiMode) ? (storedMode as UiMode) : "trader";
}

export function setCurrentUiMode(mode: UiMode) {
  window.localStorage.setItem("quantgrid_ui_mode", mode);
  window.dispatchEvent(new CustomEvent("quantgrid-ui-mode-change", { detail: mode }));
}
