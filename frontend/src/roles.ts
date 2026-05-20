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
  "/execution": ["admin", "trader"],
  "/live": ["admin", "trader", "analyst"],
  "/analysis": ["admin", "trader", "analyst"],
  "/jobs": ["admin", "trader", "analyst", "viewer", "ops"],
  "/strategies": ["admin", "trader", "analyst"],
  "/trade": ["admin", "trader"],
};

export function getCurrentRole(): Role {
  const storedRole =
    typeof window === "undefined" ? null : window.localStorage.getItem("quantgrid_role");
  const configuredRole = import.meta.env.VITE_DEFAULT_ROLE;
  const role = storedRole ?? configuredRole ?? "viewer";

  return roles.includes(role as Role) ? (role as Role) : "viewer";
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
  return typeof window !== "undefined" && Boolean(window.localStorage.getItem("quantgrid_token"));
}

export function canAccessRoute(role: Role, path: string) {
  return routeRoles[path]?.includes(role) ?? false;
}
