import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  CreditCard,
  ExternalLink,
  Minus,
  Phone,
  Plus,
  RotateCcw,
  ShoppingCart,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import {
  cancelSubscription,
  createCheckout,
  getCatalog,
  getCommercialSummary,
  openBillingPortal,
  reactivateSubscription,
  type CatalogPrice,
} from "@/api/enterprise";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useActiveClinic } from "@/hooks/useActiveClinic";

const CART_KEY = "autogal-client-billing-cart-v1";

type Cart = Record<string, number>;

const money = (minor: number, currency = "EUR") =>
  new Intl.NumberFormat("es-ES", { style: "currency", currency }).format(minor / 100);

function readCart(): Cart {
  try {
    const raw = localStorage.getItem(CART_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.entries(parsed).reduce<Cart>((result, [id, rawQuantity]) => {
      const quantity = Math.max(0, Math.min(100, Number(rawQuantity) || 0));
      if (quantity > 0) result[id] = quantity;
      return result;
    }, {});
  } catch {
    return {};
  }
}

export function PurchasesPage() {
  const { clinics, activeClinicId, setActiveClinicId } = useActiveClinic();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [cart, setCart] = useState<Cart>(readCart);

  const catalog = useQuery({ queryKey: ["billing", "catalog"], queryFn: getCatalog });
  const summary = useQuery({ queryKey: ["billing", "summary"], queryFn: getCommercialSummary });
  const prices = useMemo(
    () =>
      catalog.data?.flatMap((item) =>
        item.prices.map((price) => ({ ...price, product: item.product })),
      ) ?? [],
    [catalog.data],
  );

  useEffect(() => {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    const requested = searchParams.get("add");
    if (!requested || !prices.length) return;
    const code = requested === "phone_number" ? "phone_number_once" : requested;
    const price = prices.find((candidate) => candidate.code === code);
    if (price) {
      setCart((current) =>
        current[price.id] ? current : { ...current, [price.id]: 1 },
      );
      const next = new URLSearchParams(searchParams);
      next.delete("add");
      setSearchParams(next, { replace: true });
    }
  }, [prices, searchParams, setSearchParams]);

  const cartLines = useMemo(
    () =>
      prices
        .filter((price) => (cart[price.id] ?? 0) > 0)
        .map((price) => ({ price, quantity: cart[price.id] ?? 0 })),
    [cart, prices],
  );
  const oneTime = cartLines.reduce(
    (total, line) =>
      total +
      (line.price.billing_type === "one_time"
        ? line.price.unit_amount_minor * line.quantity
        : 0),
    0,
  );
  const recurring = cartLines.reduce(
    (total, line) =>
      total +
      (line.price.billing_type === "recurring"
        ? line.price.unit_amount_minor * line.quantity
        : 0),
    0,
  );
  const requiresClinic = cartLines.some(
    (line) => line.price.billing_type === "recurring",
  );

  const changeQuantity = (price: CatalogPrice, quantity: number) => {
    const safe = Math.max(0, Math.min(100, quantity));
    setCart((current) => {
      const next = { ...current };
      if (safe <= 0) delete next[price.id];
      else next[price.id] = safe;
      return next;
    });
  };

  const checkout = useMutation({
    mutationFn: () => {
      if (!cartLines.length) throw new Error("Añade al menos un producto a la cesta.");
      if (requiresClinic && !activeClinicId) {
        throw new Error("Selecciona o crea una clínica antes de contratar una mensualidad.");
      }
      return createCheckout(
        activeClinicId,
        cartLines.map(({ price, quantity }) => ({ price_id: price.id, quantity })),
      );
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
      toast.success(
        variables.reactivate
          ? "Reactivación solicitada a Stripe"
          : "Cancelación al final del periodo solicitada",
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (catalog.isLoading || summary.isLoading) return <LoadingState />;
  if (catalog.error) return <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />;
  if (summary.error) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const commercial = summary.data;

  return (
    <div className="space-y-7">
      <PageHeader
        title="Compras y suscripciones"
        description="Prepara la cesta y continúa el pago de forma segura en Stripe. Los importes se obtienen siempre del catálogo del servidor."
        actions={commercial?.account?.status !== "free" ? (
          <Button variant="outline" onClick={() => portal.mutate()} disabled={portal.isPending}>
            <CreditCard className="size-4" />Gestionar facturación
          </Button>
        ) : undefined}
      />

      <div className="grid gap-5 xl:grid-cols-[1.35fr_.8fr]">
        <div className="grid gap-4 sm:grid-cols-2">
          {catalog.data?.map(({ product, prices: productPrices }) => (
            <Card key={product.id}>
              <CardHeader>
                <CardTitle>{product.name}</CardTitle>
                <p className="text-sm leading-6 text-[#6f7b8d]">{product.description}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                {productPrices.map((price) => {
                  const quantity = cart[price.id] ?? 0;
                  return (
                    <div key={price.id} className="rounded-xl border border-[#e4e8ef] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold">
                            {money(price.unit_amount_minor, price.currency)}
                            {price.billing_type === "recurring" ? (
                              <span className="text-sm font-normal"> / {price.interval === "year" ? "año" : "mes"}</span>
                            ) : null}
                          </p>
                          <p className="text-xs text-[#7c8799]">
                            {price.billing_type === "one_time" ? "Pago único" : "Suscripción"}
                          </p>
                        </div>
                        {!quantity ? (
                          <Button size="sm" onClick={() => changeQuantity(price, 1)}>
                            <Plus className="size-4" />Añadir
                          </Button>
                        ) : (
                          <div className="flex items-center gap-2">
                            <Button size="icon" variant="outline" onClick={() => changeQuantity(price, quantity - 1)}>
                              <Minus className="size-4" />
                            </Button>
                            <span className="min-w-7 text-center font-semibold">{quantity}</span>
                            <Button size="icon" variant="outline" onClick={() => changeQuantity(price, quantity + 1)}>
                              <Plus className="size-4" />
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="h-fit xl:sticky xl:top-5">
          <CardHeader><CardTitle className="flex items-center gap-2"><ShoppingCart className="size-5" />Cesta</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {!cartLines.length ? (
              <div className="rounded-xl bg-[#f7f9fc] p-5 text-center text-sm text-[#718096]">
                La cesta está vacía. Añade un número o una suscripción.
              </div>
            ) : cartLines.map(({ price, quantity }) => (
              <div key={price.id} className="flex items-center justify-between gap-3 border-b pb-3">
                <div>
                  <p className="font-medium">{price.product.name}</p>
                  <p className="text-xs text-[#7c8799]">{quantity} × {money(price.unit_amount_minor, price.currency)}</p>
                </div>
                <Button size="icon" variant="ghost" onClick={() => changeQuantity(price, 0)} title="Eliminar">
                  <Trash2 className="size-4 text-[#bd3341]" />
                </Button>
              </div>
            ))}

            {requiresClinic ? (
              <label className="block text-sm font-medium">
                Clínica asociada
                <select
                  className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={activeClinicId ?? ""}
                  onChange={(event) => setActiveClinicId(event.target.value || null)}
                >
                  <option value="">Selecciona una clínica</option>
                  {clinics.map((clinic) => <option key={clinic.id} value={clinic.id}>{clinic.name}</option>)}
                </select>
                {!clinics.length ? <span className="mt-2 block text-xs text-amber-700">Las mensualidades requieren una clínica real. El número de pago único puede comprarse antes.</span> : null}
              </label>
            ) : null}

            <div className="space-y-2 border-t pt-4 text-sm">
              <div className="flex justify-between"><span>Pago único</span><strong>{money(oneTime)}</strong></div>
              <div className="flex justify-between"><span>Mensualidad</span><strong>{money(recurring)} / mes</strong></div>
              <p className="text-xs leading-5 text-[#7a8597]">Impuestos calculados por Stripe cuando correspondan. Autogal no recibe ni almacena datos de tarjeta.</p>
            </div>
            <Button
              className="w-full"
              onClick={() => checkout.mutate()}
              disabled={checkout.isPending || !cartLines.length || (requiresClinic && !activeClinicId)}
            >
              {checkout.isPending ? "Abriendo pago…" : "Continuar al pago"}<ExternalLink className="size-4" />
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatusCard title="Estado de producción" value={commercial?.can_use_production ? "Activo" : "No activo"} icon={commercial?.can_use_production ? CheckCircle2 : Clock3} positive={commercial?.can_use_production} />
        <StatusCard title="Números activos" value={String(commercial?.phone_numbers.length ?? 0)} icon={Phone} positive={Boolean(commercial?.phone_numbers.length)} />
        <StatusCard title="Provisiones pendientes" value={String(commercial?.provisioning.filter((item) => item.status !== "active").length ?? 0)} icon={Clock3} />
        <StatusCard title="Pagos fallidos" value={String(commercial?.payments.filter((item) => item.status === "failed").length ?? 0)} icon={AlertTriangle} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card><CardHeader><CardTitle>Suscripciones</CardTitle></CardHeader><CardContent className="space-y-3">{commercial?.subscriptions.length ? commercial.subscriptions.map((subscription) => <div key={subscription.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><strong className="capitalize">{subscription.status}</strong><p className="text-sm text-[#68758a]">{subscription.quantity} licencia(s)</p><p className="mt-1 text-xs text-[#8390a3]">{subscription.current_period_end ? `Periodo pagado hasta ${new Date(subscription.current_period_end).toLocaleDateString("es-ES")}` : "Sin próxima fecha disponible"}</p></div>{subscription.cancel_at_period_end ? <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">Cancelación programada</span> : <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">Renovación activa</span>}</div><div className="mt-3 flex flex-wrap gap-2">{subscription.cancel_at_period_end ? <Button size="sm" variant="outline" onClick={() => subscriptionAction.mutate({ id: subscription.id, reactivate: true })}><RotateCcw className="size-4" />Reactivar</Button> : <Button size="sm" variant="outline" onClick={() => subscriptionAction.mutate({ id: subscription.id, reactivate: false })}><XCircle className="size-4" />Cancelar al final del periodo</Button>}<Button size="sm" variant="ghost" onClick={() => portal.mutate()}><ExternalLink className="size-4" />Abrir Stripe</Button></div></div>) : <p className="text-sm text-[#788396]">Sin suscripciones</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Provisión de números</CardTitle></CardHeader><CardContent className="space-y-3">{commercial?.provisioning.length ? commercial.provisioning.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex justify-between gap-3"><strong>{item.assigned_number || "Número pendiente"}</strong><span className="text-xs font-semibold uppercase text-[#6c778b]">{item.status}</span></div><p className="mt-1 text-sm text-[#6e798c]">Cantidad: {item.quantity}</p><p className="mt-1 text-xs text-[#8390a3]">{item.status === "paid_pending_provisioning" ? item.clinic_id ? "Pago confirmado. Estará activo en menos de 24 horas y recibirás un email." : "Pago confirmado. El administrador lo vinculará a una clínica real antes de activarlo." : item.status === "active" ? `Activo desde ${item.activated_at ? new Date(item.activated_at).toLocaleDateString("es-ES") : "hoy"}` : "En proceso de configuración"}</p></div>) : <p className="text-sm text-[#788396]">Todavía no hay solicitudes de provisión.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Historial de pedidos</CardTitle></CardHeader><CardContent>{commercial?.orders.length ? commercial.orders.map((order) => <div key={order.id} className="flex justify-between gap-3 border-b py-3 text-sm"><div><strong className="capitalize">{order.status}</strong><p className="text-xs text-[#7d899c]">{new Date(order.created_at).toLocaleDateString("es-ES")}</p></div><div className="text-right"><p>{money(order.total_one_time_minor)}</p><p className="text-xs text-[#7d899c]">{money(order.total_recurring_minor)} / mes</p></div></div>) : <p className="text-sm text-[#788396]">Sin pedidos</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Pagos y facturas</CardTitle></CardHeader><CardContent>{commercial?.payments.length ? commercial.payments.map((payment) => <div key={payment.id} className="flex justify-between gap-3 border-b py-3 text-sm"><div><strong className="capitalize">{payment.status}</strong><p className="text-xs text-[#7d899c]">{new Date(payment.paid_at ?? payment.created_at).toLocaleDateString("es-ES")}{payment.failure_code ? ` · ${payment.failure_code}` : ""}</p></div><strong>{money(payment.amount_minor, payment.currency)}</strong></div>) : <p className="text-sm text-[#788396]">Sin pagos registrados</p>}</CardContent></Card>
      </div>
    </div>
  );
}

function StatusCard({ title, value, icon: Icon, positive = false }: { title:string; value:string; icon:typeof Phone; positive?:boolean }) {
  return <Card><CardContent className="flex items-center gap-3 pt-5"><span className={`rounded-xl p-2 ${positive ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}><Icon className="size-5" /></span><div><p className="text-sm text-[#6d798d]">{title}</p><p className="text-xl font-semibold">{value}</p></div></CardContent></Card>;
}
