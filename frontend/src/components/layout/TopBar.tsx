import { ChevronDown, LogOut, Menu } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useActiveClinic } from "@/hooks/useActiveClinic";
import { logout } from "@/lib/auth";

export function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const {
    clinics,
    activeClinic,
    activeClinicId,
    setActiveClinicId,
    isLoading,
  } = useActiveClinic();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleClinicChange = (clinicId: string) => {
    setActiveClinicId(clinicId || null);
    const match = location.pathname.match(/^\/clinics\/[^/]+\/(.+)$/);
    if (clinicId && match?.[1]) {
      navigate(`/clinics/${clinicId}/${match[1]}`);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      queryClient.removeQueries({ queryKey: ["auth"] });
      navigate("/login", { replace: true });
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-18 items-center justify-between gap-3 border-b border-[#e8ebf0] bg-white/90 px-4 backdrop-blur-xl sm:px-6">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onOpenMenu}
          aria-label="Abrir navegación"
        >
          <Menu className="size-5" />
        </Button>
        <div className="hidden sm:block">
          <p className="text-xs font-medium text-[#8b95a6]">
            Espacio de trabajo
          </p>
          <p className="text-sm font-semibold text-[#263249]">
            {activeClinic?.name ?? "Todas las clínicas"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative w-full max-w-[280px]">
          <Select
            aria-label="Seleccionar clínica activa"
            value={activeClinicId ?? ""}
            disabled={isLoading || !clinics.length}
            onChange={(event) => handleClinicChange(event.target.value)}
            className="appearance-none pr-9 font-medium"
          >
            {!clinics.length ? <option value="">Sin clínicas</option> : null}
            {clinics.map((clinic) => (
              <option key={clinic.id} value={clinic.id}>
                {clinic.name}
              </option>
            ))}
          </Select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[#8b95a6]" />
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleLogout}
          className="shrink-0"
        >
          <LogOut className="size-4" />
          <span className="hidden sm:inline">Cerrar sesión</span>
        </Button>
      </div>
    </header>
  );
}
