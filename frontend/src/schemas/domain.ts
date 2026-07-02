export interface Worker {
  id: string;
  clinic_id: string;
  name: string;
  role: string;
  public_description: string | null;
  calendar_id: string | null;
  color_id: string | null;
  phone_extension: string | null;
  email: string | null;
  is_active: boolean;
  working_hours_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Service {
  id: string;
  clinic_id: string;
  name: string;
  public_name: string;
  description: string | null;
  price_text: string | null;
  price_amount: string | null;
  currency: string;
  duration_minutes: number;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  requires_worker: boolean;
  allowed_worker_ids: string[] | null;
  is_bookable_by_bot: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssistantConfig {
  id: string;
  clinic_id: string;
  name: string;
  realtime_model: string;
  realtime_voice: string;
  language: string;
  temperature: string | null;
  first_message: string;
  system_prompt: string;
  safety_prompt: string;
  booking_policy_prompt: string;
  cancellation_policy_prompt: string;
  transfer_policy_prompt: string;
  tone: "profesional" | "cercano" | "comercial" | "breve" | "formal";
  response_length: "corta" | "normal" | "detallada";
  ask_patient_name: boolean;
  ask_patient_phone: boolean;
  ask_general_reason: boolean;
  allow_booking_without_worker: boolean;
  max_proposed_slots: number;
  allow_cancellations: boolean;
  allow_reschedules: boolean;
  natural_confirmation_required: boolean;
  avoid_exact_confirmation_phrases: boolean;
  additional_instructions: string | null;
  forbidden_phrases: string | null;
  no_availability_message: string | null;
  missing_calendar_message: string | null;
  emergency_message: string | null;
  human_transfer_message: string | null;
  closing_message: string | null;
  use_prices: boolean;
  use_knowledge_base: boolean;
  strict_calendar_mode: boolean;
  transcript_enabled: boolean;
  recording_enabled: boolean;
  conversation_retention_days: number;
  conversation_flow_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type ConversationFlowStepType =
  | "message"
  | "collect"
  | "tool"
  | "confirmation";

export interface ConversationFlowStep {
  id: string;
  type: ConversationFlowStepType;
  text?: string;
  field?: string;
  required?: boolean;
  tool_name?: string;
}

export interface ConversationFlowDefinition {
  name: string;
  objectives?: string[];
  exit_conditions?: string[];
  steps: ConversationFlowStep[];
}

export interface ConversationFlow {
  id: string;
  clinic_id: string;
  name: string;
  description: string | null;
  flow_json: ConversationFlowDefinition;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationFlowTemplate {
  key: string;
  name: string;
  description: string;
  flow_json: ConversationFlowDefinition;
}

export interface AssistantOptions {
  default_model: string;
  default_voice: string;
  models: Array<{ id: string; label: string; recommended: boolean }>;
  voices: Array<{ id: string; label: string; recommended: boolean }>;
  languages: Array<{ id: string; label: string; recommended: boolean }>;
}

export interface PromptPreview {
  clinic_id: string;
  config_id: string;
  realtime_model: string;
  realtime_voice: string;
  language: string;
  first_message: string;
  prompt: string;
}

export interface PromptContextPreviewData {
  clinic_id: string;
  assistant_config_id: string | null;
  services: Array<{
    id: string;
    public_name: string;
    description: string | null;
    price: string;
    duration_minutes: number;
    total_duration_minutes: number;
    requires_worker: boolean;
    worker_names: string[];
    is_bookable_by_bot: boolean;
  }>;
  workers: Array<{
    id: string;
    name: string;
    role: string;
    calendar_linked: boolean;
  }>;
  knowledge_items: Array<{
    id: string;
    title: string;
    category: KnowledgeCategory;
    content: string;
    priority: number;
  }>;
  warnings: string[];
}

export type KnowledgeCategory =
  | "prices"
  | "services"
  | "faq"
  | "policy"
  | "location"
  | "insurance"
  | "custom";

export interface KnowledgeItem {
  id: string;
  clinic_id: string;
  title: string;
  category: KnowledgeCategory;
  content: string;
  source_type: "manual" | "pdf" | "url";
  source: string | null;
  imported_at: string | null;
  import_status: string;
  is_active: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeImportPreview {
  title: string;
  category: KnowledgeCategory;
  content: string;
  source_type: "pdf" | "url";
  source: string;
  imported_at: string;
  import_status: string;
  character_count: number;
}

export type CallStatus =
  | "incoming"
  | "active"
  | "completed"
  | "failed"
  | "transferred";

export type CallOutcome =
  | "appointment_created"
  | "cancelled"
  | "transferred"
  | "no_action"
  | "failed";

export interface Call {
  id: string;
  clinic_id: string | null;
  phone_number_id: string | null;
  assistant_config_id: string | null;
  openai_call_id: string;
  provider_call_id: string | null;
  caller_phone: string;
  caller_name: string | null;
  called_number: string;
  status: CallStatus;
  detected_intent: string | null;
  outcome: CallOutcome | null;
  recording_enabled: boolean;
  transcript_enabled: boolean;
  conversation_state_json: Record<string, unknown>;
  transcript_text: string | null;
  summary_text: string | null;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CallEvent {
  id: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface CallAppointment {
  id: string;
  worker_id: string;
  worker_name: string;
  service_id: string | null;
  service_name: string | null;
  patient_name: string;
  patient_phone: string;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  source: "voice_bot" | "admin_panel";
  google_event_id: string;
}

export interface CallAnalysis extends Call {
  duration_seconds: number | null;
  appointment_created: boolean;
  appointment: CallAppointment | null;
}

export interface CallAnalysisDetail extends CallAnalysis {
  clinic_name: string;
  events: CallEvent[];
  tool_calls: CallEvent[];
  errors: CallEvent[];
}

export interface CallDebugResponse {
  call: CallAnalysisDetail;
  generated_at: string;
}

export interface CallPrivacyResponse {
  status:
    | "content_deleted"
    | "phone_anonymized"
    | "deleted"
    | "anonymized";
  call_session_id: string;
  appointment_preserved: boolean;
}

export type AppointmentStatus =
  | "pending"
  | "confirmed"
  | "cancelled"
  | "failed";

export interface Appointment {
  id: string;
  clinic_id: string;
  worker_id: string;
  service_id: string | null;
  call_session_id: string | null;
  google_calendar_id: string;
  google_event_id: string;
  patient_name: string;
  patient_phone: string;
  reason: string | null;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  source: "voice_bot" | "admin_panel";
  created_at: string;
  updated_at: string;
}

export interface AppointmentAnalysis extends Appointment {
  worker_name: string;
  service_name: string | null;
}

export interface CalendarStatus {
  clinic_id: string;
  connected: boolean;
  needs_reauthorization: boolean;
  account_email: string | null;
  workers_total: number;
  workers_linked: number;
}

export interface GoogleOAuthDiagnosticIssue {
  variable: string;
  severity: "error" | "warning";
  message: string;
  help: string;
}

export interface GoogleOAuthDiagnostics {
  clinic_id: string;
  configured: boolean;
  can_start_oauth: boolean;
  connected: boolean;
  needs_reauthorization: boolean;
  account_email: string | null;
  redirect_uri: string | null;
  public_base_url: string | null;
  frontend_base_url: string;
  issues: GoogleOAuthDiagnosticIssue[];
}

export interface GoogleOAuthStartUrl {
  clinic_id: string;
  authorization_url: string;
}

export interface CalendarInfo {
  id: string;
  summary: string;
  primary: boolean;
  access_role: string | null;
  color_id: string | null;
  background_color: string | null;
  foreground_color: string | null;
  time_zone: string | null;
}

export interface CalendarList {
  calendars: CalendarInfo[];
  event_colors: Array<{
    id: string;
    background: string;
    foreground: string;
  }>;
}

export interface WorkerCalendarResult {
  worker_id: string;
  calendar_id: string;
  color_id: string | null;
  calendar: CalendarInfo;
}

export interface WorkerFreeBusyResult {
  worker_id: string;
  calendar_id: string;
  time_min: string;
  time_max: string;
  busy_ranges: Array<{
    start_at: string;
    end_at: string;
  }>;
}

export interface TestToolTrace {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface TestChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
  action: string | null;
  tool_calls: TestToolTrace[];
}

export interface TestExtractedState {
  patient_name: string | null;
  patient_phone: string | null;
  service_name: string | null;
  worker_name: string | null;
  preferred_date: string | null;
  preferred_time_window: string | null;
  phase: string;
  appointment_confirmed: boolean;
  appointment_id: string | null;
  emergency_detected: boolean;
}

export interface TestSession {
  id: string;
  clinic_id: string;
  assistant_config_id: string;
  assistant_config_name: string;
  use_real_calendar: boolean;
  engine: "simulator" | "openai";
  prompt: string;
  messages: TestChatMessage[];
  state: TestExtractedState;
  tool_calls: TestToolTrace[];
  warnings: string[];
  is_closed: boolean;
  created_at: string;
  updated_at: string;
}

export interface SetupStatusItem {
  key: string;
  label: string;
  completed: boolean;
  automatic: boolean;
  href: string;
  help: string;
}

export interface SetupStatus {
  clinic_id: string;
  completed: boolean;
  items: SetupStatusItem[];
  warnings: string[];
  blocking_errors: string[];
}

export interface DashboardLastCall {
  id: string;
  caller_phone: string;
  called_number: string;
  status: CallStatus;
  outcome: CallOutcome | null;
  started_at: string;
}

export interface ClinicDashboard {
  clinic_id: string;
  configuration_complete: boolean;
  google_calendar_connected: boolean;
  phone_number_configured: boolean;
  assistant_active: boolean;
  active_workers: number;
  bookable_services: number;
  calls_last_24h: number;
  upcoming_appointments: number;
  recent_errors: number;
  last_call: DashboardLastCall | null;
}
