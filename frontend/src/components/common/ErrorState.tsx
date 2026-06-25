import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const message =
    error instanceof Error ? error.message : "Ha ocurrido un error inesperado.";
  return (
    <div className="rounded-2xl border border-[#ffd9dd] bg-[#fff7f8] p-5">
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-[#c73242]" />
        <div>
          <h3 className="font-semibold text-[#8e2632]">No se pudieron cargar los datos</h3>
          <p className="mt-1 text-sm text-[#9b4b54]">{message}</p>
          {onRetry ? (
            <Button className="mt-4" size="sm" variant="outline" onClick={onRetry}>
              Reintentar
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
