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
  const role =
    typeof window === "undefined"
      ? import.meta.env.VITE_DEFAULT_ROLE ?? "viewer"
      : window.localStorage.getItem("quantgrid_role") ?? import.meta.env.VITE_DEFAULT_ROLE ?? "viewer";

  config.headers.set("X-QuantGrid-Role", role);
  return config;
});

export default API;
