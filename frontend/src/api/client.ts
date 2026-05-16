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

export default API;
