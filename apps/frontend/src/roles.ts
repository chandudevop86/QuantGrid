export type Role = "admin" | "developer" | "trader" | "analyst" | "viewer" | "ops";

export const roles: Role[] = ["admin", "developer", "trader", "analyst", "viewer", "ops"];

export const roleLabels: Record<Role, string> = {
  admin: "Admin",
  developer: "Developer",
  trader: "Trader",
  analyst: "Analyst",
  viewer: "Viewer",
  ops: "Ops",
};

export const routeRoles: Record<string, Role[]> = {
  "/": ["admin", "developer", "trader", "analyst", "viewer", "ops"],
  "/candles": ["admin", "trader", "viewer"],
  "/option-chain": ["admin", "developer", "trader", "analyst", "viewer", "ops"],
  "/dhan-login": ["admin"],
  "/execution": ["admin", "trader"],
  "/live": ["admin"],
  "/analysis": ["admin"],
  "/jobs": ["admin", "developer"],
  "/operations": ["admin", "developer"],
  "/signals": ["admin", "trader"],
  "/strategies": ["admin", "developer", "trader", "viewer"],
  "/trade-journal": ["admin", "developer", "trader", "analyst", "viewer", "ops"],
  "/trade": ["admin", "trader"],
  "/admin/users": ["admin"],
  "/admin/notifications": ["admin", "developer"],
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
  if (role === "admin") return true;
  return routeRoles[path]?.includes(role) ?? false;
}
