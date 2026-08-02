import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { registerAccount } from "@/api/registration";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function RegisterPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    repeat_password: "",
    accepted_terms: false,
    accepted_privacy: false,
  });
  const mutation = useMutation({
    mutationFn: () => registerAccount(form),
    onSuccess: (identity) => {
      queryClient.setQueryData(["auth", "me"], identity);
      queryClient.removeQueries({ queryKey: ["clinics"] });
      queryClient.removeQueries({ queryKey: ["billing", "summary"] });
      toast.success("Cuenta creada. Ya has iniciado sesión.");
      navigate("/", { replace: true });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return (
    <main className="grid min-h-screen place-items-center bg-[#f5f7fb] p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Crear cuenta en Autogal</CardTitle>
          <p className="text-sm text-[#6f7a8d]">
            Entrarás directamente al Dashboard. Podrás crear tu clínica o comprar primero un número.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {([
            ["name", "Nombre"],
            ["email", "Correo electrónico"],
            ["password", "Contraseña"],
            ["repeat_password", "Repetir contraseña"],
          ] as const).map(([key, label]) => (
            <div key={key}>
              <Label>{label}</Label>
              <Input
                type={key.includes("password") ? "password" : key === "email" ? "email" : "text"}
                value={form[key]}
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
              />
            </div>
          ))}
          <label className="flex gap-2 text-sm">
            <input type="checkbox" checked={form.accepted_terms} onChange={(event) => setForm({ ...form, accepted_terms: event.target.checked })} />
            Acepto los términos de uso
          </label>
          <label className="flex gap-2 text-sm">
            <input type="checkbox" checked={form.accepted_privacy} onChange={(event) => setForm({ ...form, accepted_privacy: event.target.checked })} />
            Acepto la política de privacidad
          </label>
          <Button className="w-full" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "Creando cuenta…" : "Registrarse"}
          </Button>
          <p className="text-center text-sm">¿Ya tienes cuenta? <Link className="text-[#315efb]" to="/login">Acceder</Link></p>
        </CardContent>
      </Card>
    </main>
  );
}
