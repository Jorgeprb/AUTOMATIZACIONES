import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  Download,
  Merge,
  Plus,
  Search,
  Settings2,
  Trash2,
  Upload,
  UserRound,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  anonymizeCustomer,
  createCustomer,
  createCustomerField,
  deleteCustomer,
  deleteCustomerField,
  exportCustomers,
  getCustomer,
  importCustomers,
  listCustomerFields,
  listCustomers,
  mergeCustomers,
  updateCustomer,
  updateCustomerField,
  type ClinicCustomer,
  type CustomerDetail,
  type CustomerFieldDefinition,
  type CustomerFieldPayload,
  type CustomerFieldType,
} from "@/api/enterprise";
import { listWorkers } from "@/api/workers";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useClinicRoute } from "@/hooks/useClinicRoute";

interface CustomerFormState {
  name: string;
  phone: string;
  email: string;
  notes: string;
  preferred_worker_id: string;
  personalization_enabled: boolean;
  custom_values_json: Record<string, unknown>;
}

const emptyCustomer: CustomerFormState = {
  name: "",
  phone: "",
  email: "",
  notes: "",
  preferred_worker_id: "",
  personalization_enabled: true,
  custom_values_json: {},
};

const emptyField: CustomerFieldPayload = {
  key: "",
  label: "",
  field_type: "text",
  options_json: [],
  required: false,
  is_active: true,
  sort_order: 0,
};

export function CustomersPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [customerDialogOpen, setCustomerDialogOpen] = useState(false);
  const [detailCustomerId, setDetailCustomerId] = useState<string | null>(null);
  const [fieldsOpen, setFieldsOpen] = useState(false);
  const [mergeSource, setMergeSource] = useState<ClinicCustomer | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [editing, setEditing] = useState<ClinicCustomer | null>(null);
  const [deletingCustomer, setDeletingCustomer] = useState<ClinicCustomer | null>(null);
  const [form, setForm] = useState<CustomerFormState>(emptyCustomer);
  const [editingField, setEditingField] = useState<CustomerFieldDefinition | null>(null);
  const [fieldForm, setFieldForm] = useState<CustomerFieldPayload>(emptyField);
  const fileRef = useRef<HTMLInputElement>(null);

  const customersQuery = useQuery({
    queryKey: ["customers", clinicId, search],
    queryFn: () => listCustomers(clinicId as string, search, true),
    enabled: Boolean(clinicId),
  });
  const fieldsQuery = useQuery({
    queryKey: ["customer-fields", clinicId],
    queryFn: () => listCustomerFields(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const workersQuery = useQuery({
    queryKey: ["workers", clinicId, "customer-select"],
    queryFn: () => listWorkers(clinicId as string, true),
    enabled: Boolean(clinicId),
  });
  const detailQuery = useQuery({
    queryKey: ["customer-detail", clinicId, detailCustomerId],
    queryFn: () => getCustomer(clinicId as string, detailCustomerId as string),
    enabled: Boolean(clinicId && detailCustomerId),
  });

  const workers = workersQuery.data?.items ?? [];
  const workerNames = useMemo(
    () => new Map(workers.map((worker) => [worker.id, worker.name])),
    [workers],
  );
  const refreshCustomers = () =>
    queryClient.invalidateQueries({ queryKey: ["customers", clinicId] });

  const saveCustomer = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        notes: form.notes || null,
        preferred_worker_id: form.preferred_worker_id || null,
        personalization_enabled: form.personalization_enabled,
        custom_values_json: form.custom_values_json,
      };
      return editing
        ? updateCustomer(clinicId as string, editing.id, payload)
        : createCustomer(clinicId as string, payload);
    },
    onSuccess: async (customer) => {
      await refreshCustomers();
      await queryClient.invalidateQueries({
        queryKey: ["customer-detail", clinicId, customer.id],
      });
      setCustomerDialogOpen(false);
      toast.success(editing ? "Cliente actualizado" : "Cliente creado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const anonymize = useMutation({
    mutationFn: (id: string) => anonymizeCustomer(clinicId as string, id),
    onSuccess: async () => {
      await refreshCustomers();
      setDetailCustomerId(null);
      toast.success("Cliente anonimizado sin eliminar su historial");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const removeCustomer = useMutation({
    mutationFn: (id: string) => deleteCustomer(clinicId as string, id),
    onSuccess: async () => {
      await refreshCustomers();
      setDetailCustomerId(null);
      setDeletingCustomer(null);
      toast.success("Cliente eliminado de forma segura");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const merge = useMutation({
    mutationFn: () =>
      mergeCustomers(clinicId as string, mergeSource?.id as string, mergeTargetId),
    onSuccess: async (target) => {
      await refreshCustomers();
      setMergeSource(null);
      setMergeTargetId("");
      setDetailCustomerId(target.id);
      toast.success("Duplicados fusionados y el historial ha sido conservado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const saveField = useMutation({
    mutationFn: () =>
      editingField
        ? updateCustomerField(clinicId as string, editingField.id, fieldForm)
        : createCustomerField(clinicId as string, fieldForm),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["customer-fields", clinicId] });
      setEditingField(null);
      setFieldForm(emptyField);
      toast.success("Campo personalizado guardado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const removeField = useMutation({
    mutationFn: (id: string) => deleteCustomerField(clinicId as string, id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["customer-fields", clinicId] });
      toast.success("Campo eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const startCustomer = (row?: ClinicCustomer) => {
    setEditing(row ?? null);
    setForm(
      row
        ? {
            name: row.name,
            phone: row.display_phone,
            email: row.email ?? "",
            notes: row.notes ?? "",
            preferred_worker_id: row.preferred_worker_id ?? "",
            personalization_enabled: row.personalization_enabled,
            custom_values_json: row.custom_values_json,
          }
        : emptyCustomer,
    );
    setCustomerDialogOpen(true);
  };
  const download = async () => {
    const blob = await exportCustomers(clinicId as string);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "clientes.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const upload = async (file: File) => {
    try {
      const result = await importCustomers(clinicId as string, file);
      await refreshCustomers();
      toast.success(
        `${result.created} creados, ${result.updated} actualizados y ${result.skipped} omitidos`,
      );
      if (result.errors.length) toast.warning(result.errors.slice(0, 3).join(" · "));
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  if (customersQuery.isLoading) return <LoadingState rows={7} />;
  if (customersQuery.isError)
    return <ErrorState error={customersQuery.error} onRetry={() => customersQuery.refetch()} />;

  const customers = customersQuery.data ?? [];
  const customFields = fieldsQuery.data ?? [];
  return (
    <div className="space-y-7">
      <PageHeader
        title="Clientes"
        description="CRM privado de esta clínica: datos, preferencias, citas y llamadas."
        actions={
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileRef}
              className="hidden"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) =>
                event.target.files?.[0] && void upload(event.target.files[0])
              }
            />
            <Button variant="outline" onClick={() => setFieldsOpen(true)}>
              <Settings2 className="size-4" /> Campos
            </Button>
            <Button variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload className="size-4" /> Importar CSV
            </Button>
            <Button variant="outline" onClick={() => void download()}>
              <Download className="size-4" /> Exportar
            </Button>
            <Button onClick={() => startCustomer()}>
              <Plus className="size-4" /> Nuevo cliente
            </Button>
          </div>
        }
      />

      <div className="relative max-w-2xl">
        <Search className="absolute left-3 top-3 size-4 text-[#8b96a8]" />
        <Input
          className="pl-9"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar por nombre o teléfono"
        />
      </div>

      {!customers.length ? (
        <EmptyState
          icon={UserRound}
          title="Aún no hay clientes"
          description="Los clientes creados manualmente o después de una reserva aparecerán aquí."
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-[#e4e8ef] bg-white">
          <div className="hidden grid-cols-[minmax(180px,1.2fr)_180px_minmax(180px,1fr)_150px_84px] gap-4 border-b bg-[#f8fafc] px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#718096] md:grid">
            <span>Cliente</span><span>Teléfono</span><span>Profesional</span><span>Último contacto</span><span>Acciones</span>
          </div>
          {customers.map((row) => (
            <div
              key={row.id}
              className="grid gap-2 border-b px-5 py-3 transition last:border-b-0 hover:bg-[#f8fbff] md:grid-cols-[minmax(180px,1.2fr)_180px_minmax(180px,1fr)_150px_84px] md:items-center md:gap-4"
            >
              <button type="button" className="text-left" onClick={() => setDetailCustomerId(row.id)}>
                <strong className="block text-[#172033]">{row.name}</strong><small className="text-[#748094]">{row.email ?? "Sin email"}</small>
              </button>
              <span className="text-sm text-[#566277]">{row.display_phone}</span>
              <span className="text-sm text-[#566277]">{row.preferred_worker_id ? workerNames.get(row.preferred_worker_id) ?? "Profesional eliminado" : "Sin preferencia"}</span>
              <span className="text-sm text-[#748094]">{formatDate(row.last_contact_at)}</span>
              <div className="flex justify-end gap-1">
                <Button size="icon" variant="ghost" title="Editar" onClick={() => startCustomer(row)}><Settings2 className="size-4" /></Button>
                <Button size="icon" variant="ghost" title="Eliminar" onClick={() => setDeletingCustomer(row)}><Trash2 className="size-4 text-[#bd3341]" /></Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <CustomerFormDialog
        open={customerDialogOpen}
        onOpenChange={setCustomerDialogOpen}
        editing={editing}
        form={form}
        setForm={setForm}
        fields={customFields}
        workers={workers.map((worker) => ({ id: worker.id, name: worker.name }))}
        pending={saveCustomer.isPending}
        onSave={() => saveCustomer.mutate()}
      />
      <CustomerDetailDialog
        detail={detailQuery.data}
        loading={detailQuery.isLoading}
        open={Boolean(detailCustomerId)}
        onOpenChange={(open) => !open && setDetailCustomerId(null)}
        workerNames={workerNames}
        clinicId={clinicId as string}
        onEdit={(customer) => startCustomer(customer)}
        onAnonymize={(customer) => anonymize.mutate(customer.id)}
        onMerge={(customer) => {
          setMergeSource(customer);
          setMergeTargetId("");
        }}
      />
      <FieldsDialog
        open={fieldsOpen}
        onOpenChange={setFieldsOpen}
        fields={customFields}
        editing={editingField}
        form={fieldForm}
        setForm={setFieldForm}
        onEdit={(field) => {
          setEditingField(field);
          setFieldForm({
            key: field.key,
            label: field.label,
            field_type: field.field_type,
            options_json: field.options_json,
            required: field.required,
            is_active: field.is_active,
            sort_order: field.sort_order,
          });
        }}
        onReset={() => { setEditingField(null); setFieldForm(emptyField); }}
        onSave={() => saveField.mutate()}
        onDelete={(id) => removeField.mutate(id)}
        pending={saveField.isPending}
      />
      <ConfirmDialog
        open={Boolean(deletingCustomer)}
        onOpenChange={(open) => !open && setDeletingCustomer(null)}
        title="Eliminar cliente"
        description="Si tiene citas o llamadas, sus datos serán anonimizados y se conservarán los snapshots históricos. Si no tiene referencias, se eliminará físicamente."
        confirmLabel="Eliminar cliente"
        isPending={removeCustomer.isPending}
        onConfirm={() => deletingCustomer && removeCustomer.mutate(deletingCustomer.id)}
      />

      <Dialog open={Boolean(mergeSource)} onOpenChange={(open) => !open && setMergeSource(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Fusionar duplicado</DialogTitle></DialogHeader>
          <p className="text-sm text-[#657186]">Las citas y llamadas de <strong>{mergeSource?.name}</strong> pasarán al cliente de destino y el registro de origen se eliminará.</p>
          <Label>Cliente que se conservará</Label>
          <Select value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)}>
            <option value="">Selecciona un cliente</option>
            {customers.filter((customer) => customer.id !== mergeSource?.id).map((customer) => <option key={customer.id} value={customer.id}>{customer.name} · {customer.display_phone}</option>)}
          </Select>
          <Button disabled={!mergeTargetId || merge.isPending} onClick={() => merge.mutate()}><Merge className="size-4" />{merge.isPending ? "Fusionando…" : "Fusionar historiales"}</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CustomerFormDialog({ open, onOpenChange, editing, form, setForm, fields, workers, pending, onSave }: {
  open: boolean; onOpenChange: (open: boolean) => void; editing: ClinicCustomer | null;
  form: CustomerFormState; setForm: (form: CustomerFormState) => void;
  fields: CustomerFieldDefinition[]; workers: Array<{id:string;name:string}>; pending: boolean; onSave: () => void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[90vh] overflow-y-auto"><DialogHeader><DialogTitle>{editing ? "Editar cliente" : "Nuevo cliente"}</DialogTitle></DialogHeader><div className="space-y-4">
    <Field label="Nombre"><Input value={form.name} onChange={(event) => setForm({...form,name:event.target.value})}/></Field>
    <Field label="Teléfono"><Input value={form.phone} onChange={(event) => setForm({...form,phone:event.target.value})} placeholder="+34 600 000 000"/></Field>
    <Field label="Email"><Input type="email" value={form.email} onChange={(event) => setForm({...form,email:event.target.value})}/></Field>
    <Field label="Profesional preferido"><Select value={form.preferred_worker_id} onChange={(event) => setForm({...form,preferred_worker_id:event.target.value})}><option value="">Sin preferencia</option>{workers.map((worker)=><option key={worker.id} value={worker.id}>{worker.name}</option>)}</Select></Field>
    <Field label="Notas"><Textarea value={form.notes} onChange={(event) => setForm({...form,notes:event.target.value})}/></Field>
    {fields.filter((field)=>field.is_active).map((field)=><CustomValueInput key={field.id} field={field} value={form.custom_values_json[field.key]} onChange={(value)=>setForm({...form,custom_values_json:{...form.custom_values_json,[field.key]:value}})}/>) }
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.personalization_enabled} onChange={(event)=>setForm({...form,personalization_enabled:event.target.checked})}/>Permitir personalización por nombre</label>
    <Button className="w-full" disabled={!form.name || !form.phone || pending} onClick={onSave}>{pending ? "Guardando…" : "Guardar"}</Button>
  </div></DialogContent></Dialog>;
}

function CustomerDetailDialog({ detail, loading, open, onOpenChange, workerNames, clinicId, onEdit, onAnonymize, onMerge }: {
  detail?: CustomerDetail; loading: boolean; open: boolean; onOpenChange: (open:boolean)=>void;
  workerNames: Map<string,string>; clinicId:string;
  onEdit:(customer:ClinicCustomer)=>void; onAnonymize:(customer:ClinicCustomer)=>void; onMerge:(customer:ClinicCustomer)=>void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto"><DialogHeader><DialogTitle>Ficha del cliente</DialogTitle></DialogHeader>{loading || !detail ? <LoadingState rows={5}/> : <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4 rounded-xl bg-[#f7f9fc] p-4"><div><h3 className="text-xl font-semibold text-[#172033]">{detail.name}</h3><p className="text-sm text-[#657186]">{detail.display_phone} · {detail.email ?? "sin email"}</p><p className="mt-1 text-xs text-[#8490a2]">Último contacto: {formatDate(detail.last_contact_at)}</p></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={()=>onEdit(detail)}>Editar</Button><Button size="sm" variant="outline" asChild><Link to={`/clinics/${clinicId}/calendar?customer_id=${detail.id}`}><CalendarPlus className="size-4"/>Nueva cita</Link></Button><Button size="sm" variant="ghost" onClick={()=>onMerge(detail)}><Merge className="size-4"/>Fusionar</Button></div></div>
    <div className="grid gap-4 md:grid-cols-2"><InfoCard title="Preferencias"><p>Profesional: {detail.preferred_worker_id ? workerNames.get(detail.preferred_worker_id) ?? "No disponible" : "Sin preferencia"}</p><p>Personalización: {detail.personalization_enabled ? "Permitida" : "Desactivada"}</p></InfoCard><InfoCard title="Notas"><p className="whitespace-pre-wrap">{detail.notes || "Sin notas"}</p></InfoCard></div>
    {Object.keys(detail.custom_values_json).length > 0 && <InfoCard title="Datos personalizados"><dl className="grid gap-2 sm:grid-cols-2">{Object.entries(detail.custom_values_json).map(([key,value])=><div key={key}><dt className="text-xs font-semibold uppercase text-[#8792a4]">{key}</dt><dd>{formatUnknown(value)}</dd></div>)}</dl></InfoCard>}
    <InfoCard title={`Historial de citas (${detail.appointments.length})`}><div className="space-y-2">{detail.appointments.length ? detail.appointments.map((appointment)=><div key={appointment.id} className="flex flex-wrap justify-between gap-2 border-b py-2 text-sm"><span>{new Date(appointment.start_at).toLocaleString("es-ES")}</span><span>{workerNames.get(appointment.worker_id) ?? "Profesional"}</span><span className="rounded-full bg-slate-100 px-2 py-1 text-xs">{appointment.status}</span></div>) : <p>Sin citas relacionadas.</p>}</div></InfoCard>
    <InfoCard title={`Historial de llamadas (${detail.calls.length})`}><div className="space-y-2">{detail.calls.length ? detail.calls.map((call)=><div key={call.id} className="border-b py-2 text-sm"><div className="flex flex-wrap justify-between gap-2"><span>{new Date(call.started_at).toLocaleString("es-ES")}</span><span>{call.outcome || call.status}</span></div>{call.summary_text && <p className="mt-1 text-[#657186]">{call.summary_text}</p>}</div>) : <p>Sin llamadas relacionadas.</p>}</div></InfoCard>
    <div className="flex flex-wrap justify-end gap-2"><Button variant="destructive" onClick={()=>onAnonymize(detail)}>Anonimizar datos</Button></div>
  </div>}</DialogContent></Dialog>;
}

function FieldsDialog({ open, onOpenChange, fields, editing, form, setForm, onEdit, onReset, onSave, onDelete, pending }: {
  open:boolean; onOpenChange:(open:boolean)=>void; fields:CustomerFieldDefinition[]; editing:CustomerFieldDefinition|null;
  form:CustomerFieldPayload; setForm:(value:CustomerFieldPayload)=>void; onEdit:(field:CustomerFieldDefinition)=>void; onReset:()=>void; onSave:()=>void; onDelete:(id:string)=>void; pending:boolean;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto"><DialogHeader><DialogTitle>Campos personalizados</DialogTitle></DialogHeader><div className="grid gap-6 md:grid-cols-[1fr_1fr]">
    <div className="space-y-3">{fields.length ? fields.map((field)=><Card key={field.id}><CardContent className="flex items-start justify-between gap-3 pt-5"><div><strong>{field.label}</strong><p className="text-xs text-[#748094]">{field.key} · {field.field_type}{field.required ? " · obligatorio" : ""}</p></div><div className="flex gap-1"><Button size="sm" variant="ghost" onClick={()=>onEdit(field)}>Editar</Button><Button size="sm" variant="ghost" onClick={()=>onDelete(field.id)}>Eliminar</Button></div></CardContent></Card>) : <p className="text-sm text-[#657186]">Crea campos para guardar información específica de esta clínica.</p>}</div>
    <div className="space-y-4 rounded-xl border p-4"><h3 className="font-semibold">{editing ? "Editar campo" : "Nuevo campo"}</h3><Field label="Clave"><Input value={form.key} disabled={Boolean(editing)} onChange={(event)=>setForm({...form,key:event.target.value.toLowerCase().replace(/[^a-z0-9_]/g,"_")})}/></Field><Field label="Etiqueta"><Input value={form.label} onChange={(event)=>setForm({...form,label:event.target.value})}/></Field><Field label="Tipo"><Select value={form.field_type} onChange={(event)=>setForm({...form,field_type:event.target.value as CustomerFieldType})}>{["text","textarea","number","boolean","date","select"].map((type)=><option key={type} value={type}>{type}</option>)}</Select></Field>{form.field_type === "select" && <Field label="Opciones (una por línea)"><Textarea value={form.options_json.join("\n")} onChange={(event)=>setForm({...form,options_json:event.target.value.split("\n").map((item)=>item.trim()).filter(Boolean)})}/></Field>}<Field label="Orden"><Input type="number" min={0} value={form.sort_order} onChange={(event)=>setForm({...form,sort_order:Number(event.target.value)})}/></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.required} onChange={(event)=>setForm({...form,required:event.target.checked})}/>Obligatorio</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_active} onChange={(event)=>setForm({...form,is_active:event.target.checked})}/>Activo</label><div className="flex gap-2"><Button disabled={!form.key||!form.label||pending} onClick={onSave}>{pending?"Guardando…":"Guardar"}</Button>{editing && <Button variant="outline" onClick={onReset}>Cancelar</Button>}</div></div>
  </div></DialogContent></Dialog>;
}

function CustomValueInput({ field, value, onChange }: { field:CustomerFieldDefinition; value:unknown; onChange:(value:unknown)=>void }) {
  if (field.field_type === "boolean") return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(value)} onChange={(event)=>onChange(event.target.checked)}/>{field.label}{field.required ? " *" : ""}</label>;
  if (field.field_type === "textarea") return <Field label={`${field.label}${field.required ? " *" : ""}`}><Textarea value={typeof value === "string" ? value : ""} onChange={(event)=>onChange(event.target.value)}/></Field>;
  if (field.field_type === "select") return <Field label={`${field.label}${field.required ? " *" : ""}`}><Select value={typeof value === "string" ? value : ""} onChange={(event)=>onChange(event.target.value)}><option value="">Selecciona</option>{field.options_json.map((option)=><option key={option} value={option}>{option}</option>)}</Select></Field>;
  return <Field label={`${field.label}${field.required ? " *" : ""}`}><Input type={field.field_type === "number" ? "number" : field.field_type === "date" ? "date" : "text"} value={typeof value === "string" || typeof value === "number" ? String(value) : ""} onChange={(event)=>onChange(field.field_type === "number" && event.target.value !== "" ? Number(event.target.value) : event.target.value)}/></Field>;
}

function Field({ label, children }: { label:string; children:React.ReactNode }) { return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>; }
function InfoCard({ title, children }: { title:string; children:React.ReactNode }) { return <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader><CardContent className="space-y-1 text-sm text-[#566277]">{children}</CardContent></Card>; }
function formatDate(value:string|null) { return value ? new Date(value).toLocaleDateString("es-ES") : "Sin contacto"; }
function formatUnknown(value:unknown) { if (typeof value === "boolean") return value ? "Sí" : "No"; if (value === null || value === undefined || value === "") return "—"; return Array.isArray(value) ? value.join(", ") : String(value); }
