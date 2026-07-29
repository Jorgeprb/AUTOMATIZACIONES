import { useQuery } from "@tanstack/react-query";

import { getCommercialSummary } from "@/api/enterprise";
import { isClientPortal } from "@/lib/portal";

export function useCommercialAccess() {
  const query = useQuery({
    queryKey: ["billing", "summary"],
    queryFn: getCommercialSummary,
    enabled: isClientPortal,
    staleTime: 30_000,
    retry: false,
  });

  return {
    ...query,
    summary: query.data ?? null,
    unlocked: !isClientPortal || Boolean(query.data?.portal_unlocked),
    isResolving: isClientPortal && query.isLoading,
  };
}
