export type Role = "admin" | "trader" | "analyst" | "viewer" | "ops";

export const roles: Role[] = ["admin", "trader", "analyst", "viewer", "ops"];

export const roleLabels: Record<Role, string> = {
  admin: "Admin",
  trader: "Trader",
  analyst: "Analyst",
  viewer: "Viewer",
  ops: "Ops",
};

export const routeRoles: Record<string, Role[]> = {
  "/": ["admin", "trader", "analyst", "viewer", "ops"],
  "/candles": ["admin", "trader", "analyst", "viewer"],
  "/option-chain": ["admin", "trader", "analyst", "viewer"],
  "/dhan-login": ["admin", "trader"],
  "/execution": ["admin", "trader"],
  "/live": ["admin", "trader", "analyst"],
  "/analysis": ["admin", "trader", "analyst"],
  "/jobs": ["admin", "trader", "analyst", "viewer", "ops"],
  "/operations": ["admin", "trader", "analyst", "viewer", "ops"],
  "/signals": ["admin", "trader", "analyst", "viewer", "ops"],
  "/strategies": ["admin", "trader", "analyst"],
  "/trade": ["admin", "trader"],
  "/admin/users": ["admin"],
  "/admin/notifications": ["admin"],
};

type AuthClaims = {
  role?: string;
  exp?: number;
  uid?: number;
};

function decodeAuthClaims(): AuthClaims | null {
  if (typeof window === "undefined") return null;

  const token = window.localStorage.getItem("quantgrid_token");
  if (!token) return null;

  const [payload] = token.split(".");
  if (!payload) return null;

  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    return JSON.parse(window.atob(padded)) as AuthClaims;
  } catch {
    return null;
  }
}

export function getCurrentRole(): Role {
  const claims = decodeAuthClaims();
  const role = claims?.role ?? "viewer";

  return roles.includes(role as Role) ? (role as Role) : "viewer";
}

export function getCurrentUserId(): number | null {
  const claims = decodeAuthClaims();
  return typeof claims?.uid === "number" ? claims.uid : null;
}

export function setCurrentRole(role: Role) {
  window.localStorage.setItem("quantgrid_role", role);
  window.dispatchEvent(new CustomEvent("quantgrid-role-change", { detail: role }));
}

export function setCurrentAuth(role: Role, token: string) {
  window.localStorage.setItem("quantgrid_role", role);
  window.localStorage.setItem("quantgrid_token", token);
  window.dispatchEvent(new CustomEvent("quantgrid-role-change", { detail: role }));
}

export function clearCurrentAuth() {
  window.localStorage.removeItem("quantgrid_role");
  window.localStorage.removeItem("quantgrid_token");
  window.dispatchEvent(new CustomEvent("quantgrid-role-change", { detail: "viewer" }));
}

export function hasAuthToken() {
  const claims = decodeAuthClaims();
  if (!claims?.exp || !roles.includes(claims.role as Role)) return false;
  return claims.exp * 1000 > Date.now();
}

export function canAccessRoute(role: Role, path: string) {
  return routeRoles[path]?.includes(role) ?? false;
}
