import { Navigate, useLocation } from "react-router-dom";
import { canAccessRoute, getCurrentRole } from "../roles";

type RequireRoleProps = {
  children: React.ReactNode;
  path: string;
};

export default function RequireRole({ children, path }: RequireRoleProps) {
  const role = getCurrentRole();
  const location = useLocation();

  if (!canAccessRoute(role, path)) {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
