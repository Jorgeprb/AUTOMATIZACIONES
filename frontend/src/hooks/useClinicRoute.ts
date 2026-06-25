import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { useActiveClinic } from "@/hooks/useActiveClinic";

export function useClinicRoute(): string | null {
  const { clinicId } = useParams<{ clinicId: string }>();
  const { activeClinicId, setActiveClinicId } = useActiveClinic();

  useEffect(() => {
    if (clinicId && clinicId !== activeClinicId) {
      setActiveClinicId(clinicId);
    }
  }, [activeClinicId, clinicId, setActiveClinicId]);

  return clinicId ?? activeClinicId;
}
