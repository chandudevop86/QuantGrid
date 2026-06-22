import axios from "axios";

const fallbackBaseURL =
  typeof window === "undefined"
    ? "http://localhost:8000"
    : import.meta.env.DEV
      ? `${window.location.origin}/api`
      : `${window.location.origin}/api`;

const configuredBaseURL =
  import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? fallbackBaseURL;

function normalizeBaseURL(baseURL: string) {
  if (typeof window === "undefined") return baseURL;

  try {
    const target = new URL(baseURL, window.location.origin);
    const isSameHostBackendPort = target.hostname === window.location.hostname && target.port === "8000";

    if (!import.meta.env.DEV && isSameHostBackendPort) {
      return `${window.location.origin}/api`;
    }
  } catch {
    return baseURL;
  }

  return baseURL;
}

const API = axios.create({
  baseURL: normalizeBaseURL(configuredBaseURL).replace(/\/+$/, ""),
  headers: {
    "Content-Type": "application/json",
  },
});

API.interceptors.request.use((config) => {
  const mode =
    typeof window === "undefined"
      ? import.meta.env.VITE_DEFAULT_MODE ?? "paper"
      : window.location.protocol === "http:" && !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname)
        ? "paper"
        : window.localStorage.getItem("quantgrid_mode") ?? import.meta.env.VITE_DEFAULT_MODE ?? "paper";
  const token =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_token");

  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  config.headers.set("X-QuantGrid-Mode", mode);
  return config;
});

export function getApiErrorMessage(error: any, fallback = "Request failed") {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;

  if (status === 401) {
    return "Invalid username or password. Check the backend admin user in the database.";
  }
  if (status === 403) {
    return detail ?? "This account is not allowed to access that action.";
  }
  if (error?.message === "Network Error" || !error?.response) {
    return `Cannot reach the QuantGrid API at ${normalizeBaseURL(configuredBaseURL)}. Check VITE_API_URL/VITE_API_BASE_URL, CORS, and that the backend is running.`;
  }

  return detail ?? error?.message ?? fallback;
}

export default API;
