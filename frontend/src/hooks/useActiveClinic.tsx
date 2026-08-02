import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";

import { listAllClinics } from "@/api/clinics";
import type { Clinic } from "@/schemas/clinic";
import { portalMode } from "@/lib/portal";

const STORAGE_KEY = `autogal-${portalMode}-active-clinic`;

interface ActiveClinicContextValue {
  clinics: Clinic[];
  activeClinic: Clinic | null;
  activeClinicId: string | null;
  setActiveClinicId: (clinicId: string | null) => void;
  isLoading: boolean;
  error: Error | null;
}

const ActiveClinicContext = createContext<ActiveClinicContextValue | null>(null);

export function ActiveClinicProvider({ children }: { children: ReactNode }) {
  const [activeClinicId, setActiveClinicIdState] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  );
  const clinicsQuery = useQuery({
    queryKey: ["clinics", "selector"],
    queryFn: listAllClinics,
  });
  const clinics = clinicsQuery.data ?? [];

  useEffect(() => {
    if (!clinics.length) {
      if (!clinicsQuery.isLoading && activeClinicId !== null) {
        setActiveClinicIdState(null);
        localStorage.removeItem(STORAGE_KEY);
      }
      return;
    }
    const exists = clinics.some((clinic) => clinic.id === activeClinicId);
    if (!exists) {
      const firstClinicId = clinics[0]?.id ?? null;
      setActiveClinicIdState(firstClinicId);
      if (firstClinicId) localStorage.setItem(STORAGE_KEY, firstClinicId);
    }
  }, [activeClinicId, clinics, clinicsQuery.isLoading]);

  const setActiveClinicId = (clinicId: string | null) => {
    setActiveClinicIdState(clinicId);
    if (clinicId) localStorage.setItem(STORAGE_KEY, clinicId);
    else localStorage.removeItem(STORAGE_KEY);
  };

  const activeClinic =
    clinics.find((clinic) => clinic.id === activeClinicId) ?? null;

  const value = useMemo<ActiveClinicContextValue>(
    () => ({
      clinics,
      activeClinic,
      activeClinicId,
      setActiveClinicId,
      isLoading: clinicsQuery.isLoading,
      error: clinicsQuery.error,
    }),
    [
      activeClinic,
      activeClinicId,
      clinics,
      clinicsQuery.error,
      clinicsQuery.isLoading,
    ],
  );

  return (
    <ActiveClinicContext.Provider value={value}>
      {children}
    </ActiveClinicContext.Provider>
  );
}

export function useActiveClinic(): ActiveClinicContextValue {
  const context = useContext(ActiveClinicContext);
  if (!context) {
    throw new Error("useActiveClinic must be used inside ActiveClinicProvider");
  }
  return context;
}
