import axios from "axios";

const fallbackBaseURL =
  typeof window === "undefined"
    ? "http://localhost:8000"
    : `${window.location.protocol}//${window.location.hostname}:8000`;

const API = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? fallbackBaseURL,
  headers: {
    "Content-Type": "application/json",
  },
});

API.interceptors.request.use((config) => {
  const mode =
    typeof window === "undefined"
      ? import.meta.env.VITE_DEFAULT_MODE ?? "paper"
      : window.localStorage.getItem("quantgrid_mode") ?? import.meta.env.VITE_DEFAULT_MODE ?? "paper";
  const token =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_token");

  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  config.headers.set("X-QuantGrid-Mode", mode);
  return config;
});

export default API;
