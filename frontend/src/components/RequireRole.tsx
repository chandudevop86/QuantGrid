import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

type RequireRoleProps = {
  children: React.ReactNode;
  path: string;
};

export default function RequireRole({ children, path }: RequireRoleProps) {
  const [role, setRole] = useState(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const location = useLocation();

  useEffect(() => {
    const syncAuth = () => {
      setRole(getCurrentRole());
      setAuthenticated(hasAuthToken());
    };

    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  if (!authenticated && path !== "/") {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }

  if (authenticated && !canAccessRoute(role, path)) {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
