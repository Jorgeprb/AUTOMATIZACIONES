import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Chrome, LockKeyhole } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getCurrentAdmin, loginWithPassword } from "@/lib/auth";
import { isClientPortal, portalMode } from "@/lib/portal";

type LoginLocationState = { from?: string };

const authMessages: Record<string, string> = {
  account_not_invited: "Tu cuenta todavía no tiene acceso. Pide al administrador que te invite.",
  account_disabled: "Esta cuenta está desactivada.",
  domain_not_allowed: "La cuenta Google no pertenece al dominio permitido.",
  google_rejected: "Google canceló o rechazó el acceso.",
  token_exchange_failed: "No se pudo completar el acceso con Google.",
  invalid_identity: "Google no pudo verificar la identidad de la cuenta.",
  expired_state: "La solicitud de acceso caducó. Inténtalo de nuevo.",
};

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const state = location.state as LoginLocationState | null;
  const redirectTo = state?.from && state.from !== "/login" ? state.from : "/";
  const authError = useMemo(() => new URLSearchParams(location.search).get("auth_error"), [location.search]);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const authQuery = useQuery({ queryKey: ["auth", "me"], queryFn: getCurrentAdmin, retry: false, staleTime: 60_000 });

  if (authQuery.data) return <Navigate to={redirectTo} replace />;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(null); setIsSubmitting(true);
    try {
      const identity = await loginWithPassword(username, password);
      queryClient.setQueryData(["auth", "me"], identity);
      navigate(redirectTo, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo iniciar sesión.");
    } finally { setIsSubmitting(false); }
  };

  const googleHref = `/auth/login/google/start?portal=${portalMode}&return_to=${encodeURIComponent(redirectTo)}`;

  return <main className="flex min-h-screen items-center justify-center bg-[#f6f8fb] px-4 py-10">
    <Card className="w-full max-w-md">
      <CardHeader>
        <div className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-[#315efb] text-lg font-bold text-white">A</div>
        <CardTitle>{isClientPortal ? "Acceder a tu espacio Autogal" : "Acceder a administración"}</CardTitle>
        <CardDescription>{isClientPortal ? "Gestiona únicamente tus clínicas, asistentes, calendarios y conversaciones." : "Administración global de clientes y clínicas."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <Button asChild className="w-full" variant="outline"><a href={googleHref}><Chrome className="size-4" />Continuar con Google</a></Button>
        <div className="flex items-center gap-3 text-xs uppercase tracking-[0.12em] text-[#929bab]"><span className="h-px flex-1 bg-[#e1e5ec]" />o con contraseña<span className="h-px flex-1 bg-[#e1e5ec]" /></div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2"><Label htmlFor="username">Usuario o email</Label><Input id="username" autoComplete="username" autoFocus required value={username} onChange={(event) => setUsername(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="password">Contraseña</Label><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></div>
          {(error || authError) ? <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700" role="alert">{error || authMessages[authError || ""] || "No se pudo completar el acceso."}</p> : null}
          <Button className="w-full" type="submit" disabled={isSubmitting}><LockKeyhole className="size-4" />{isSubmitting ? "Entrando…" : "Entrar"}</Button>
        </form>
      </CardContent>
    </Card>
  </main>;
}
