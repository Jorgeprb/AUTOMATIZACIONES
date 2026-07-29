import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock3, CreditCard, ExternalLink, Phone, RotateCcw, ShoppingCart, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  cancelSubscription,
  createCheckout,
  getCatalog,
  getCommercialSummary,
  openBillingPortal,
  reactivateSubscription,
} from "@/api/enterprise";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useClinicRoute } from "@/hooks/useClinicRoute";

const money = (minor: number, currency = "EUR") =>
  new Intl.NumberFormat("es-ES", { style: "currency", currency }).format(minor / 100);

export function PurchasesPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [quantity, setQuantity] = useState(1);
  const catalog = useQuery({ queryKey: ["billing", "catalog"], queryFn: getCatalog });
  const summary = useQuery({ queryKey: ["billing", "summary"], queryFn: getCommercialSummary });
  const prices = useMemo(
    () => catalog.data?.flatMap((item) => item.prices.map((price) => ({ ...price, product: item.product }))) ?? [],
    [catalog.data],
  );
  const phone = prices.find((price) => price.code === "phone_number_once");
  const monthly = prices.find((price) => price.code === "monthly_service");
  const checkout = useMutation({
    mutationFn: () => {
      if (!phone || !monthly || !clinicId) throw new Error("Catálogo no configurado");
      return createCheckout(clinicId, [
        { price_id: phone.id, quantity },
        { price_id: monthly.id, quantity },
      ]);
    },
    onSuccess: (result) => window.location.assign(result.checkout_url),
    onError: (error: Error) => toast.error(error.message),
  });
  const portal = useMutation({
    mutationFn: openBillingPortal,
    onSuccess: (result) => window.location.assign(result.url),
    onError: (error: Error) => toast.error(error.message),
  });
  const subscriptionAction = useMutation({
    mutationFn: ({ id, reactivate }: { id: string; reactivate: boolean }) =>
      reactivate ? reactivateSubscription(id) : cancelSubscription(id),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["billing", "summary"] });
      toast.success(variables.reactivate ? "Reactivación solicitada a Stripe" : "Cancelación al final del periodo solicitada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (catalog.isLoading || summary.isLoading) return <LoadingState rows={7} />;
  if (catalog.isError) return <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  const initial = (phone?.unit_amount_minor ?? 0) * quantity;
  const recurring = (monthly?.unit_amount_minor ?? 0) * quantity;
  const commercial = summary.data;
  return (
    <div className="space-y-7">
      <PageHeader
        title="Compras y suscripciones"
        description="Contrata números y gestiona el servicio mensual. El pago se realiza en Stripe Checkout."
        actions={<Button variant="outline" onClick={() => portal.mutate()} disabled={portal.isPending}><CreditCard className="size-4" />Gestionar o cancelar suscripción</Button>}
      />
      <Card className="border-[#b8c8ff] bg-[#f4f7ff]"><CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold text-[#20345f]">Prueba gratuitamente el asistente llamando al +34 881 17 08 37 antes de contratar.</p><p className="mt-1 text-sm text-[#65718a]">Es una demostración y todavía no utiliza tu propio número. El número contratado se activa en menos de 24 horas.</p></div><Button asChild><a href="tel:+34881170837"><Phone className="size-4" />Llamar a la demo</a></Button></CardContent></Card>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="grid gap-4 md:grid-cols-2">
          {catalog.data?.map((item) => <Card key={item.product.id}><CardHeader><CardTitle>{item.product.name}</CardTitle></CardHeader><CardContent><p className="min-h-12 text-sm text-[#677388]">{item.product.description}</p>{item.prices.map((price) => <p key={price.id} className="mt-4 text-2xl font-bold">{money(price.unit_amount_minor, price.currency)}{price.billing_type === "recurring" ? <span className="text-sm font-normal"> / {price.interval === "month" ? "mes" : "año"}</span> : null}</p>)}</CardContent></Card>)}
        </div>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShoppingCart className="size-5" />Resumen</CardTitle></CardHeader><CardContent className="space-y-4"><label className="block text-sm font-medium">Cantidad de números/licencias<Input className="mt-2" type="number" min={1} max={100} value={quantity} onChange={(event) => setQuantity(Math.max(1, Number(event.target.value)))} /></label><div className="space-y-2 border-t pt-4 text-sm"><div className="flex justify-between"><span>Pago inicial</span><strong>{money(initial)}</strong></div><div className="flex justify-between"><span>Mensualidad</span><strong>{money(recurring)} / mes</strong></div><p className="text-xs text-[#7a8597]">Impuestos calculados por Stripe cuando correspondan. Autogal no recibe ni almacena los datos de la tarjeta.</p></div><Button className="w-full" onClick={() => checkout.mutate()} disabled={checkout.isPending || !phone || !monthly}>{checkout.isPending ? "Abriendo pago…" : "Continuar al pago"}<ExternalLink className="size-4" /></Button></CardContent></Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatusCard title="Estado de producción" value={commercial?.can_use_production ? "Activo" : "No activo"} icon={commercial?.can_use_production ? CheckCircle2 : Clock3} positive={commercial?.can_use_production} />
        <StatusCard title="Números activos" value={String(commercial?.phone_numbers.length ?? 0)} icon={Phone} positive={Boolean(commercial?.phone_numbers.length)} />
        <StatusCard title="Provisiones pendientes" value={String(commercial?.provisioning.filter((item) => item.status !== "active").length ?? 0)} icon={Clock3} />
        <StatusCard title="Pagos fallidos" value={String(commercial?.payments.filter((item) => item.status === "failed").length ?? 0)} icon={AlertTriangle} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card><CardHeader><CardTitle>Suscripciones</CardTitle></CardHeader><CardContent className="space-y-3">{commercial?.subscriptions.length ? commercial.subscriptions.map((subscription) => <div key={subscription.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><strong className="capitalize">{subscription.status}</strong><p className="text-sm text-[#68758a]">{subscription.quantity} licencia(s)</p><p className="mt-1 text-xs text-[#8390a3]">{subscription.current_period_end ? `Periodo pagado hasta ${new Date(subscription.current_period_end).toLocaleDateString("es-ES")}` : "Sin próxima fecha disponible"}</p></div>{subscription.cancel_at_period_end ? <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">Cancelación programada</span> : <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">Renovación activa</span>}</div><div className="mt-3 flex flex-wrap gap-2">{subscription.cancel_at_period_end ? <Button size="sm" variant="outline" onClick={() => subscriptionAction.mutate({ id: subscription.id, reactivate: true })}><RotateCcw className="size-4" />Reactivar</Button> : <Button size="sm" variant="outline" onClick={() => subscriptionAction.mutate({ id: subscription.id, reactivate: false })}><XCircle className="size-4" />Cancelar al final del periodo</Button>}<Button size="sm" variant="ghost" onClick={() => portal.mutate()}><ExternalLink className="size-4" />Abrir Stripe</Button></div></div>) : <p className="text-sm text-[#788396]">Sin suscripciones</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Provisión de números</CardTitle></CardHeader><CardContent className="space-y-3">{commercial?.provisioning.length ? commercial.provisioning.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex justify-between gap-3"><strong>{item.assigned_number || "Número pendiente"}</strong><span className="text-xs font-semibold uppercase text-[#6c778b]">{item.status}</span></div><p className="mt-1 text-sm text-[#6e798c]">Cantidad: {item.quantity}{item.provider ? ` · ${item.provider}` : ""}</p><p className="mt-1 text-xs text-[#8390a3]">{item.status === "paid_pending_provisioning" ? "Pago confirmado. Estará activo en menos de 24 horas y recibirás un email." : item.status === "active" ? `Activo desde ${item.activated_at ? new Date(item.activated_at).toLocaleDateString("es-ES") : "hoy"}` : "En proceso de configuración"}</p></div>) : <p className="text-sm text-[#788396]">Todavía no hay solicitudes de provisión.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Historial de pedidos</CardTitle></CardHeader><CardContent>{commercial?.orders.length ? commercial.orders.map((order) => <div key={order.id} className="flex justify-between gap-3 border-b py-3 text-sm"><div><strong className="capitalize">{order.status}</strong><p className="text-xs text-[#7d899c]">{new Date(order.created_at).toLocaleDateString("es-ES")}</p></div><div className="text-right"><p>{money(order.total_one_time_minor)}</p><p className="text-xs text-[#7d899c]">{money(order.total_recurring_minor)} / mes</p></div></div>) : <p className="text-sm text-[#788396]">Sin pedidos</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Pagos y facturas</CardTitle></CardHeader><CardContent>{commercial?.payments.length ? commercial.payments.map((payment) => <div key={payment.id} className="flex justify-between gap-3 border-b py-3 text-sm"><div><strong className="capitalize">{payment.status}</strong><p className="text-xs text-[#7d899c]">{new Date(payment.paid_at ?? payment.created_at).toLocaleDateString("es-ES")}{payment.failure_code ? ` · ${payment.failure_code}` : ""}</p></div><strong>{money(payment.amount_minor, payment.currency)}</strong></div>) : <p className="text-sm text-[#788396]">Sin pagos registrados</p>}</CardContent></Card>
      </div>
    </div>
  );
}

function StatusCard({ title, value, icon: Icon, positive = false }: { title:string; value:string; icon:typeof Phone; positive?:boolean }) {
  return <Card><CardContent className="flex items-center gap-3 pt-5"><span className={`rounded-xl p-2 ${positive ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}><Icon className="size-5" /></span><div><p className="text-sm text-[#6d798d]">{title}</p><p className="text-xl font-semibold">{value}</p></div></CardContent></Card>;
}
