import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { LoadingState } from "@/components/common/LoadingState";
import { getCurrentAdmin } from "@/lib/auth";
import { adminPortalUrl, clientPortalUrl, isAdminPortal, isClientPortal } from "@/lib/portal";

export function RequireAuth() {
  const location = useLocation();
  const navigate = useNavigate();
  const authQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getCurrentAdmin,
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    const onUnauthorized = () => {
      navigate("/login", {
        replace: true,
        state: { from: location.pathname + location.search },
      });
    };
    window.addEventListener("autogal:unauthorized", onUnauthorized);
    return () => window.removeEventListener("autogal:unauthorized", onUnauthorized);
  }, [location.pathname, location.search, navigate]);

  if (authQuery.isPending) {
    return <div className="p-8"><LoadingState rows={5} /></div>;
  }

  if (authQuery.data) {
    if (isAdminPortal && authQuery.data.role !== "super_admin") {
      window.location.replace(clientPortalUrl);
      return <LoadingState rows={3} />;
    }
    if (isClientPortal && authQuery.data.role === "super_admin") {
      window.location.replace(adminPortalUrl);
      return <LoadingState rows={3} />;
    }
  }

  if (authQuery.isError || !authQuery.data) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <Outlet context={{ admin: authQuery.data }} />;
}
