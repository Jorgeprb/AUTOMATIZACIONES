import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Building2, CreditCard, Euro, PackagePlus, PhoneCall, ReceiptText, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import {
  createAdminPrice,
  createAdminProduct,
  getGlobalAnalytics,
  listAdminPrices,
  listAdminProducts,
  listBillingAccounts,
  listProvisioning,
  updateAdminPrice,
  updateAdminProduct,
  updateProvisioning,
  type CatalogPrice,
  type CatalogPricePayload,
  type CatalogProduct,
  type CatalogProductPayload,
  type ProvisioningOrder,
} from "@/api/enterprise";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { MetricCard } from "@/components/common/MetricCard";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const productInitial: CatalogProductPayload = {
  code: "",
  name: "",
  description: "",
  product_type: "one_time",
  ownership_type: "service",
  entitlement_code: "",
  quantity_configurable: true,
  stripe_product_id: "",
  is_active: true,
};
const priceInitial: CatalogPricePayload = {
  product_id: "",
  code: "",
  currency: "EUR",
  unit_amount_minor: 0,
  billing_type: "one_time",
  interval: null,
  stripe_price_id: "",
  is_active: true,
};

export function BusinessAdminPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const stats = useQuery({ queryKey: ["global-analytics"], queryFn: getGlobalAnalytics });
  const accounts = useQuery({ queryKey: ["billing-accounts"], queryFn: listBillingAccounts });
  const provisioning = useQuery({ queryKey: ["provisioning"], queryFn: listProvisioning });
  const products = useQuery({ queryKey: ["admin-products"], queryFn: listAdminProducts });
  const prices = useQuery({ queryKey: ["admin-prices"], queryFn: listAdminPrices });
  const [editingProvisioning, setEditingProvisioning] = useState<ProvisioningOrder | null>(null);
  const [provisioningForm, setProvisioningForm] = useState({ clinic_id: "", assigned_number: "", provider: "voipstudio", external_provider_id: "", sip_target: "sip:bot@sip.autogal.es:6060;transport=udp", webhook_url: "", notes: "", status: "paid_pending_provisioning" });
  const [editingProduct, setEditingProduct] = useState<CatalogProduct | "new" | null>(null);
  const [productForm, setProductForm] = useState<CatalogProductPayload>(productInitial);
  const [editingPrice, setEditingPrice] = useState<CatalogPrice | "new" | null>(null);
  const [priceForm, setPriceForm] = useState<CatalogPricePayload>(priceInitial);

  const saveProvisioning = useMutation({
    mutationFn: () => updateProvisioning(editingProvisioning!.id, provisioningForm),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["provisioning"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-users"] }),
        queryClient.invalidateQueries({ queryKey: ["billing-accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["global-analytics"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "global-analytics"] }),
      ]);
      setEditingProvisioning(null);
      toast.success(
        provisioningForm.status === "active"
          ? "Número asignado y notificación encolada"
          : "Provisión actualizada",
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const saveProduct = useMutation({
    mutationFn: () => editingProduct === "new" ? createAdminProduct(productForm) : updateAdminProduct(editingProduct!.id, productForm),
    onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ["admin-products"] }), queryClient.invalidateQueries({ queryKey: ["billing", "catalog"] })]); setEditingProduct(null); toast.success("Producto guardado"); },
    onError: (error: Error) => toast.error(error.message),
  });
  const savePrice = useMutation({
    mutationFn: () => editingPrice === "new" ? createAdminPrice(priceForm) : updateAdminPrice(editingPrice!.id, priceForm),
    onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ["admin-prices"] }), queryClient.invalidateQueries({ queryKey: ["billing", "catalog"] })]); setEditingPrice(null); toast.success("Precio guardado"); },
    onError: (error: Error) => toast.error(error.message),
  });

  const startProvisioning = (row: ProvisioningOrder, assignNow = false) => {
    setEditingProvisioning(row);
    setProvisioningForm({
      clinic_id: row.clinic_id ?? "",
      assigned_number: row.assigned_number ?? "",
      provider: row.provider ?? "voipstudio",
      external_provider_id: row.external_provider_id ?? "",
      sip_target:
        row.sip_target ?? "sip:bot@sip.autogal.es:6060;transport=udp",
      webhook_url: row.webhook_url ?? "",
      notes: row.notes ?? "",
      status: assignNow ? "active" : row.status,
    });
  };
  const provisioningId = searchParams.get("provisioning");
  useEffect(() => {
    if (!provisioningId || !provisioning.data) return;
    const row = provisioning.data.find((item) => item.id === provisioningId);
    if (row) startProvisioning(row, searchParams.get("mode") === "assign");
    setSearchParams({}, { replace: true });
  }, [provisioning.data, provisioningId, searchParams, setSearchParams]);

  const startProduct = (row?: CatalogProduct) => {
    setEditingProduct(row ?? "new");
    setProductForm(row ? { ...row, description: row.description ?? "", entitlement_code: row.entitlement_code ?? "", stripe_product_id: row.stripe_product_id ?? "" } : productInitial);
  };
  const startPrice = (row?: CatalogPrice) => {
    setEditingPrice(row ?? "new");
    setPriceForm(row ? { ...row, stripe_price_id: row.stripe_price_id ?? "" } : { ...priceInitial, product_id: products.data?.[0]?.id ?? "" });
  };

  if ([stats, accounts, provisioning, products, prices].some((query) => query.isLoading)) return <LoadingState rows={9} />;
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => stats.refetch()} />;

  const pendingRows = provisioning.data?.filter((row) => row.status === "paid_pending_provisioning") ?? [];
  const provisioningAccount = editingProvisioning
    ? accounts.data?.find((account) => account.id === editingProvisioning.billing_account_id)
    : null;
  const provisioningClinics = provisioningAccount?.clinics ?? [];
  const provisioningClinicName = provisioningClinics.find(
    (clinic) => clinic.id === provisioningForm.clinic_id,
  )?.name ?? null;

  return <div className="space-y-7">
    <PageHeader title="Negocio y provisión" description="Cuentas comerciales, catálogo, MRR, pagos y cola de números." />
    {pendingRows.length ? (
      <Card className="border-[#f0c5ca] bg-[#fff5f6]">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
          <span className="grid size-11 place-items-center rounded-xl bg-[#ffe4e7] text-[#b62f40]"><AlertTriangle className="size-5" /></span>
          <div className="flex-1"><p className="font-semibold text-[#932a38]">Hay {pendingRows.length} número(s) pendiente(s) de activar</p><p className="mt-1 text-sm text-[#9b4d58]">El pago está confirmado. Asigna el número y marca la provisión como activa.</p></div>
          <Button variant="outline" onClick={() => startProvisioning(pendingRows[0]!)}>Gestionar ahora</Button>
        </CardContent>
      </Card>
    ) : null}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard icon={Building2} label="Clínicas" value={String(stats.data?.clinics ?? 0)} />
      <MetricCard icon={ShieldCheck} label="Suscripciones activas" value={String(stats.data?.active_subscriptions ?? 0)} accent="green" />
      <MetricCard icon={Euro} label="MRR" value={`${((stats.data?.mrr_minor ?? 0) / 100).toFixed(2)} €`} accent="amber" />
      <MetricCard icon={ReceiptText} label="Provisiones pendientes" value={String(stats.data?.pending_provisioning ?? 0)} accent="violet" />
    </div>

    <div className="grid gap-5 xl:grid-cols-2">
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Building2 className="size-5" />Cuentas comerciales</CardTitle></CardHeader><CardContent className="space-y-3">{accounts.data?.map((account) => <div key={account.id} className="rounded-lg border p-3"><div className="flex justify-between gap-3"><strong>{account.display_name}</strong><span className="text-sm capitalize">{account.status}</span></div><p className="text-sm text-[#6e798d]">{account.billing_email} · {account.owner ?? "Sin propietario"}</p><p className="mt-1 text-sm">{account.clinics.map((clinic) => clinic.name).join(", ") || "Sin clínicas"}</p></div>)}</CardContent></Card>
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><PhoneCall className="size-5" />Provisión de números</CardTitle></CardHeader><CardContent className="space-y-3">{provisioning.data?.map((row) => <div key={row.id} className="flex items-center justify-between gap-3 rounded-lg border p-3"><div><strong>{row.assigned_number || "Número pendiente"}</strong><p className="text-sm text-[#6e798d]">{row.status} · {new Date(row.created_at).toLocaleDateString()}</p></div><Button size="sm" variant="outline" onClick={() => startProvisioning(row)}>Gestionar</Button></div>)}</CardContent></Card>
    </div>

    <div className="grid gap-5 xl:grid-cols-2">
      <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle>Productos</CardTitle><Button size="sm" onClick={() => startProduct()}><PackagePlus className="size-4" />Nuevo</Button></CardHeader><CardContent className="space-y-3">{products.data?.map((row) => <button key={row.id} type="button" className="w-full rounded-lg border p-3 text-left hover:bg-[#f7f9fc]" onClick={() => startProduct(row)}><div className="flex justify-between gap-2"><strong>{row.name}</strong><span className="text-xs uppercase">{row.is_active ? "Activo" : "Inactivo"}</span></div><p className="text-sm text-[#6e798d]">{row.code} · {row.product_type} · {row.ownership_type}</p></button>)}</CardContent></Card>
      <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle>Precios</CardTitle><Button size="sm" onClick={() => startPrice()} disabled={!products.data?.length}><PackagePlus className="size-4" />Nuevo</Button></CardHeader><CardContent className="space-y-3">{prices.data?.map((row) => <button key={row.id} type="button" className="w-full rounded-lg border p-3 text-left hover:bg-[#f7f9fc]" onClick={() => startPrice(row)}><div className="flex justify-between gap-2"><strong>{(row.unit_amount_minor / 100).toFixed(2)} {row.currency}</strong><span>{row.billing_type === "recurring" ? `/${row.interval}` : "pago único"}</span></div><p className="text-sm text-[#6e798d]">{row.code} · {products.data?.find((product) => product.id === row.product_id)?.name ?? row.product_id}</p></button>)}</CardContent></Card>
    </div>

    <Dialog open={Boolean(editingProvisioning)} onOpenChange={(open) => !open && setEditingProvisioning(null)}><DialogContent><DialogHeader><DialogTitle>{provisioningForm.status === "active" ? `Añadir número a ${provisioningClinicName ?? "una clínica"}` : "Gestionar provisión"}</DialogTitle><p className="text-sm leading-6 text-[#6f7b90]">Selecciona una clínica real de la cuenta. Al guardar como activo, el número quedará asignado y se enviará automáticamente un correo al cliente.</p></DialogHeader><div className="space-y-3"><div><Label>Clínica</Label><select className="w-full rounded-md border p-2" value={provisioningForm.clinic_id} onChange={(event) => setProvisioningForm({ ...provisioningForm, clinic_id: event.target.value })}><option value="">Selecciona una clínica</option>{provisioningClinics.map((clinic) => <option key={clinic.id} value={clinic.id}>{clinic.name}</option>)}</select>{!provisioningClinics.length ? <p className="mt-1 text-xs text-amber-700">Esta cuenta todavía no tiene clínicas. Créala desde Usuarios y clínicas.</p> : null}</div>{([['assigned_number','Número asignado'],['provider','Proveedor'],['external_provider_id','ID externo'],['sip_target','SIP target'],['webhook_url','Webhook'],['notes','Notas']] as const).map(([key,label]) => <div key={key}><Label>{label}</Label><Input value={provisioningForm[key]} onChange={(event) => setProvisioningForm({ ...provisioningForm, [key]: event.target.value })} /></div>)}<Label>Estado</Label><select className="w-full rounded-md border p-2" value={provisioningForm.status} onChange={(event) => setProvisioningForm({ ...provisioningForm, status: event.target.value })}><option value="paid_pending_provisioning">Pago confirmado, pendiente</option><option value="provisioned">Aprovisionado</option><option value="active">Activo</option><option value="failed">Fallido</option></select><Button className="w-full" onClick={() => saveProvisioning.mutate()} disabled={saveProvisioning.isPending || (provisioningForm.status === "active" && (!provisioningForm.clinic_id || !provisioningForm.assigned_number.trim()))}><CreditCard className="size-4" />{provisioningForm.status === "active" ? "Asignar número y notificar" : "Guardar"}</Button></div></DialogContent></Dialog>

    <Dialog open={Boolean(editingProduct)} onOpenChange={(open) => !open && setEditingProduct(null)}><DialogContent><DialogHeader><DialogTitle>{editingProduct === "new" ? "Nuevo producto" : "Editar producto"}</DialogTitle></DialogHeader><div className="space-y-3"><div><Label>Código</Label><Input value={productForm.code} onChange={(event) => setProductForm({ ...productForm, code: event.target.value })} /></div><div><Label>Nombre</Label><Input value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></div><div><Label>Descripción</Label><Input value={productForm.description ?? ""} onChange={(event) => setProductForm({ ...productForm, description: event.target.value })} /></div><div className="grid grid-cols-2 gap-3"><div><Label>Tipo</Label><select className="w-full rounded-md border p-2" value={productForm.product_type} onChange={(event) => setProductForm({ ...productForm, product_type: event.target.value as CatalogProductPayload["product_type"] })}><option value="one_time">Pago único</option><option value="subscription">Suscripción</option><option value="addon">Complemento</option></select></div><div><Label>Propiedad</Label><select className="w-full rounded-md border p-2" value={productForm.ownership_type} onChange={(event) => setProductForm({ ...productForm, ownership_type: event.target.value as CatalogProductPayload["ownership_type"] })}><option value="permanent">Permanente</option><option value="service">Servicio</option></select></div></div><div><Label>Entitlement</Label><Input value={productForm.entitlement_code ?? ""} onChange={(event) => setProductForm({ ...productForm, entitlement_code: event.target.value || null })} /></div><div><Label>Stripe Product ID</Label><Input value={productForm.stripe_product_id ?? ""} onChange={(event) => setProductForm({ ...productForm, stripe_product_id: event.target.value || null })} /></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={productForm.quantity_configurable} onChange={(event) => setProductForm({ ...productForm, quantity_configurable: event.target.checked })} />Cantidad configurable</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={productForm.is_active} onChange={(event) => setProductForm({ ...productForm, is_active: event.target.checked })} />Activo</label><Button className="w-full" onClick={() => saveProduct.mutate()} disabled={saveProduct.isPending || !productForm.code || !productForm.name}>Guardar producto</Button></div></DialogContent></Dialog>

    <Dialog open={Boolean(editingPrice)} onOpenChange={(open) => !open && setEditingPrice(null)}><DialogContent><DialogHeader><DialogTitle>{editingPrice === "new" ? "Nuevo precio" : "Editar precio"}</DialogTitle></DialogHeader><div className="space-y-3"><div><Label>Producto</Label><select className="w-full rounded-md border p-2" value={priceForm.product_id} onChange={(event) => setPriceForm({ ...priceForm, product_id: event.target.value })}>{products.data?.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></div><div><Label>Código</Label><Input value={priceForm.code} onChange={(event) => setPriceForm({ ...priceForm, code: event.target.value })} /></div><div className="grid grid-cols-2 gap-3"><div><Label>Importe en céntimos</Label><Input type="number" min={0} value={priceForm.unit_amount_minor} onChange={(event) => setPriceForm({ ...priceForm, unit_amount_minor: Number(event.target.value) })} /></div><div><Label>Moneda</Label><Input value={priceForm.currency} onChange={(event) => setPriceForm({ ...priceForm, currency: event.target.value.toUpperCase() })} /></div></div><div className="grid grid-cols-2 gap-3"><div><Label>Facturación</Label><select className="w-full rounded-md border p-2" value={priceForm.billing_type} onChange={(event) => { const billing_type = event.target.value as CatalogPricePayload["billing_type"]; setPriceForm({ ...priceForm, billing_type, interval: billing_type === "recurring" ? "month" : null }); }}><option value="one_time">Pago único</option><option value="recurring">Recurrente</option></select></div><div><Label>Intervalo</Label><select className="w-full rounded-md border p-2" value={priceForm.interval ?? ""} disabled={priceForm.billing_type === "one_time"} onChange={(event) => setPriceForm({ ...priceForm, interval: event.target.value as "month" | "year" })}><option value="month">Mes</option><option value="year">Año</option></select></div></div><div><Label>Stripe Price ID</Label><Input value={priceForm.stripe_price_id ?? ""} onChange={(event) => setPriceForm({ ...priceForm, stripe_price_id: event.target.value || null })} /></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={priceForm.is_active} onChange={(event) => setPriceForm({ ...priceForm, is_active: event.target.checked })} />Activo</label><Button className="w-full" onClick={() => savePrice.mutate()} disabled={savePrice.isPending || !priceForm.product_id || !priceForm.code}>Guardar precio</Button></div></DialogContent></Dialog>
  </div>;
}
