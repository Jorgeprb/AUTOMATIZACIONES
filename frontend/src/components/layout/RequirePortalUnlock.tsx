import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { LoadingState } from "@/components/common/LoadingState";
import { useCommercialAccess } from "@/hooks/useCommercialAccess";
import { isClientPortal } from "@/lib/portal";

export function RequirePortalUnlock({ children }: { children: ReactNode }) {
  const access = useCommercialAccess();
  if (!isClientPortal) return children;
  if (access.isResolving) return <LoadingState rows={5} />;
  if (!access.unlocked) return <Navigate to="/" replace />;
  return children;
}
