import { apiBlobRequest, apiRequest, toQuery } from "@/api/client";

export interface ClinicCustomer {
  id: string;
  clinic_id: string;
  name: string;
  normalized_phone: string;
  display_phone: string;
  email: string | null;
  notes: string | null;
  custom_values_json: Record<string, unknown>;
  preferred_worker_id: string | null;
  personalization_enabled: boolean;
  is_active: boolean;
  first_contact_at: string | null;
  last_contact_at: string | null;
}


export interface RelatedAppointment {
  id: string; patient_name: string; patient_phone: string; start_at: string; end_at: string;
  status: string; worker_id: string; service_id: string;
}
export interface RelatedCall {
  id: string; caller_name: string | null; caller_phone: string; status: string; outcome: string;
  started_at: string; ended_at: string | null; summary_text: string | null;
}
export interface CustomerDetail extends ClinicCustomer {
  appointments: RelatedAppointment[]; calls: RelatedCall[];
}
export type CustomerFieldType = "text" | "textarea" | "number" | "boolean" | "date" | "select";
export interface CustomerFieldDefinition {
  id: string; clinic_id: string; key: string; label: string; field_type: CustomerFieldType;
  options_json: string[]; required: boolean; is_active: boolean; sort_order: number;
  created_at: string; updated_at: string;
}
export interface CustomerFieldPayload {
  key: string; label: string; field_type: CustomerFieldType; options_json: string[];
  required: boolean; is_active: boolean; sort_order: number;
}

export interface CustomerPayload {
  name: string;
  phone: string;
  email?: string | null;
  notes?: string | null;
  custom_values_json?: Record<string, unknown>;
  preferred_worker_id?: string | null;
  personalization_enabled?: boolean;
  is_active?: boolean;
}

export interface ClinicResource {
  id: string;
  clinic_id: string;
  name: string;
  description: string | null;
  resource_type: string;
  capacity: number;
  schedule_json: Record<string, unknown>;
  is_active: boolean;
}

export interface MetricPoint { key: string; label: string; value: number }
export interface ClinicAnalytics {
  appointments_created: number;
  appointments_cancelled: number;
  appointments_completed: number;
  appointments_no_show: number;
  cancellation_rate: number;
  call_to_booking_conversion: number;
  estimated_revenue_minor: number;
  calls_answered: number;
  calls_failed: number;
  average_call_duration_seconds: number;
  new_customers: number;
  returning_customers: number;
  appointments_by_service: MetricPoint[];
  appointments_by_worker: MetricPoint[];
  appointments_by_weekday: MetricPoint[];
  appointments_by_hour: MetricPoint[];
  appointment_statuses: MetricPoint[];
  sentiments: MetricPoint[];
  timeline: MetricPoint[];
  heatmap: Array<{ key: string; value: number; day: number; hour: number }>;
}

export interface CatalogPrice {
  id: string; product_id: string; code: string; currency: string;
  unit_amount_minor: number; billing_type: "one_time" | "recurring";
  interval: "month" | "year" | null; stripe_price_id: string | null; is_active: boolean;
}
export interface CatalogProduct {
  id: string; code: string; name: string; description: string | null;
  product_type: "one_time" | "subscription" | "addon";
  ownership_type: "permanent" | "service"; entitlement_code: string | null;
  quantity_configurable: boolean; stripe_product_id: string | null; is_active: boolean;
}
export interface CatalogItem { product: CatalogProduct; prices: CatalogPrice[] }
export interface CommercialSummary {
  account: { id: string; display_name: string; billing_email: string; status: string; clinic_count: number; user_count: number; owner_email: string | null; owner_name: string | null } | null;
  orders: Array<{ id: string; status: string; total_one_time_minor: number; total_recurring_minor: number; created_at: string }>;
  subscriptions: Array<{ id: string; clinic_id: string; status: string; quantity: number; current_period_end: string | null; cancel_at_period_end: boolean; canceled_at: string | null }>;
  payments: Array<{ id: string; clinic_id: string | null; amount_minor: number; currency: string; status: string; paid_at: string | null; failure_code: string | null; created_at: string }>;
  provisioning: Array<{ id: string; clinic_id: string; status: string; quantity: number; assigned_number: string | null; provider: string | null; provisioned_at: string | null; activated_at: string | null; created_at: string }>;
  entitlements: Array<{ id: string; clinic_id: string; code: string; status: string; quantity: number }>;
  phone_numbers: string[];
  can_use_production: boolean;
}

export function listCustomers(clinicId: string, search = "", active?: boolean): Promise<ClinicCustomer[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers${toQuery({ search, active })}`);
}
export function getCustomer(clinicId: string, id: string): Promise<CustomerDetail> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers/${id}`);
}
export function createCustomer(clinicId: string, payload: CustomerPayload): Promise<ClinicCustomer> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers`, { method: "POST", body: JSON.stringify(payload) });
}
export function updateCustomer(clinicId: string, id: string, payload: Partial<CustomerPayload>): Promise<ClinicCustomer> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function anonymizeCustomer(clinicId: string, id: string): Promise<ClinicCustomer> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers/${id}/anonymize`, { method: "POST" });
}
export function mergeCustomers(clinicId: string, source: string, target: string): Promise<ClinicCustomer> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customers/merge`, { method: "POST", body: JSON.stringify({ source_customer_id: source, target_customer_id: target }) });
}
export function exportCustomers(clinicId: string): Promise<Blob> {
  return apiBlobRequest(`/api/admin/clinics/${clinicId}/customers/export.csv`);
}
export function importCustomers(clinicId: string, file: File): Promise<{created:number;updated:number;skipped:number;errors:string[]}> {
  const body = new FormData(); body.append("file", file);
  return apiRequest(`/api/admin/clinics/${clinicId}/customers/import.csv`, { method: "POST", body });
}
export function listCustomerFields(clinicId: string): Promise<CustomerFieldDefinition[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customer-fields`);
}
export function createCustomerField(clinicId: string, payload: CustomerFieldPayload): Promise<CustomerFieldDefinition> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customer-fields`, { method: "POST", body: JSON.stringify(payload) });
}
export function updateCustomerField(clinicId: string, id: string, payload: CustomerFieldPayload): Promise<CustomerFieldDefinition> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customer-fields/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function deleteCustomerField(clinicId: string, id: string): Promise<void> {
  return apiRequest(`/api/admin/clinics/${clinicId}/customer-fields/${id}`, { method: "DELETE" });
}
export function listResources(clinicId: string): Promise<ClinicResource[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/resources`);
}
export function saveResource(clinicId: string, payload: Omit<ClinicResource,"id"|"clinic_id">, id?: string): Promise<ClinicResource> {
  return apiRequest(`/api/admin/clinics/${clinicId}/resources${id ? `/${id}` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
}
export function deleteResource(clinicId: string, id: string): Promise<void> {
  return apiRequest(`/api/admin/clinics/${clinicId}/resources/${id}`, { method: "DELETE" });
}
export interface ResourceRequirement { resource_id: string; quantity: number }
export function listResourceRequirements(clinicId: string, serviceId: string): Promise<ResourceRequirement[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/services/${serviceId}/resource-requirements`);
}
export function replaceResourceRequirements(clinicId: string, serviceId: string, payload: ResourceRequirement[]): Promise<ResourceRequirement[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/services/${serviceId}/resource-requirements`, { method: "PUT", body: JSON.stringify(payload) });
}
export interface AnalyticsFilters {
  period: string; date_from?: string; date_to?: string; worker_id?: string; service_id?: string;
  phone_number?: string; appointment_status?: string;
}
export function getAnalytics(clinicId: string, filters: AnalyticsFilters): Promise<ClinicAnalytics> {
  return apiRequest(`/api/admin/clinics/${clinicId}/analytics${toQuery({ ...filters })}`);
}
export function getCatalog(): Promise<CatalogItem[]> { return apiRequest("/api/billing/catalog"); }
export function getCommercialSummary(): Promise<CommercialSummary> { return apiRequest("/api/billing/summary"); }
export function createCheckout(clinicId: string, lines: Array<{price_id:string;quantity:number}>): Promise<{order_id:string;checkout_url:string}> {
  return apiRequest("/api/billing/checkout", { method: "POST", body: JSON.stringify({ clinic_id: clinicId, lines }) });
}
export function openBillingPortal(): Promise<{url:string}> { return apiRequest("/api/billing/portal", { method: "POST" }); }
export function cancelSubscription(id:string): Promise<{status:string}> { return apiRequest(`/api/billing/subscriptions/${id}/cancel`, { method:"POST" }); }
export function reactivateSubscription(id:string): Promise<{status:string}> { return apiRequest(`/api/billing/subscriptions/${id}/reactivate`, { method:"POST" }); }

export interface ProvisioningOrder { id:string; clinic_id:string; billing_account_id:string; status:string; quantity:number; assigned_number:string|null; provider:string|null; external_provider_id:string|null; sip_target:string|null; webhook_url:string|null; notes:string|null; created_at:string; }
export function getGlobalAnalytics():Promise<Record<string,number>>{return apiRequest('/api/admin/analytics/global');}
export function listBillingAccounts():Promise<Array<{id:string;display_name:string;billing_email:string;status:string;owner:string|null;clinics:Array<{id:string;name:string}>;subscriptions:Array<{id:string;status:string}>;provisioning:Array<{id:string;status:string;assigned_number:string|null}>}>>{return apiRequest('/api/admin/billing/accounts');}
export function listAdminProducts():Promise<CatalogProduct[]>{return apiRequest('/api/admin/billing/products');}
export function listAdminPrices():Promise<CatalogPrice[]>{return apiRequest('/api/admin/billing/prices');}
export function listProvisioning():Promise<ProvisioningOrder[]>{return apiRequest('/api/admin/provisioning');}
export function updateProvisioning(id:string,payload:Partial<ProvisioningOrder>):Promise<ProvisioningOrder>{return apiRequest(`/api/admin/provisioning/${id}`,{method:'PATCH',body:JSON.stringify(payload)});}

export type CatalogProductPayload = Omit<CatalogProduct, "id">;
export type CatalogPricePayload = Omit<CatalogPrice, "id">;
export function createAdminProduct(payload:CatalogProductPayload):Promise<CatalogProduct>{return apiRequest('/api/admin/billing/products',{method:'POST',body:JSON.stringify(payload)});}
export function updateAdminProduct(id:string,payload:CatalogProductPayload):Promise<CatalogProduct>{return apiRequest(`/api/admin/billing/products/${id}`,{method:'PATCH',body:JSON.stringify(payload)});}
export function createAdminPrice(payload:CatalogPricePayload):Promise<CatalogPrice>{return apiRequest('/api/admin/billing/prices',{method:'POST',body:JSON.stringify(payload)});}
export function updateAdminPrice(id:string,payload:CatalogPricePayload):Promise<CatalogPrice>{return apiRequest(`/api/admin/billing/prices/${id}`,{method:'PATCH',body:JSON.stringify(payload)});}
export function getClinicCommercial(clinicId:string):Promise<Record<string,unknown>>{return apiRequest(`/api/admin/clinics/${clinicId}/commercial`);}
