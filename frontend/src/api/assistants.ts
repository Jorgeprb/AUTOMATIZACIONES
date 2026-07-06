import { apiBlobRequest, apiConfig, apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  AssistantConfig,
  AssistantOptions,
  PromptPreview,
  VoiceCatalogVoice,
  VoiceProviderInfo,
} from "@/schemas/domain";
import type { AssistantConfigPayload } from "@/schemas/assistant";

export function listAssistantConfigs(
  clinicId: string,
  isActive?: boolean,
): Promise<Page<AssistantConfig>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs${toQuery({
      page: 1,
      page_size: 100,
      is_active: isActive,
    })}`,
  );
}

export function getAssistantOptions(): Promise<AssistantOptions> {
  return apiRequest("/api/admin/assistant-options");
}

export function listVoiceProviders(): Promise<VoiceProviderInfo[]> {
  return apiRequest("/api/admin/voice-providers");
}

export function listVoiceProviderVoices(
  provider: string,
): Promise<VoiceCatalogVoice[]> {
  return apiRequest(`/api/admin/voice-providers/${provider}/voices`);
}

export function syncVoiceProviders(): Promise<{
  ok: boolean;
  synced: Record<string, number>;
}> {
  return apiRequest("/api/admin/voice-providers/sync", { method: "POST" });
}

export function createAssistantConfig(
  clinicId: string,
  payload: AssistantConfigPayload,
): Promise<AssistantConfig> {
  return apiRequest(`/api/admin/clinics/${clinicId}/assistant-configs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAssistantConfig(
  clinicId: string,
  configId: string,
  payload: Partial<AssistantConfigPayload> & {
    conversation_flow_id?: string | null;
  },
): Promise<AssistantConfig> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/${configId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function activateAssistantConfig(
  clinicId: string,
  configId: string,
): Promise<AssistantConfig> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/${configId}/activate`,
    { method: "POST" },
  );
}

export function deleteAssistantConfig(
  clinicId: string,
  configId: string,
): Promise<{ id: string }> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/${configId}`,
    { method: "DELETE" },
  );
}

export function previewPrompt(
  clinicId: string,
  configId: string,
): Promise<PromptPreview> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/${configId}/preview-prompt`,
    { method: "POST" },
  );
}

export function previewAssistantVoice(
  clinicId: string,
  payload: {
    text: string;
    realtime_voice: string;
    realtime_model?: string | null;
    call_audio_mode?: "openai_hosted_sip" | "vps_media_bridge";
    voice_provider?: string;
    tts_model?: string | null;
    voice_id?: string | null;
    voice_locale?: string | null;
    voice_gender?: string | null;
    azure_speech_region?: string | null;
    voice_style?: string | null;
    voice_speed?: string;
    voice_pitch?: string;
    voice_stability?: string | null;
    voice_similarity?: string | null;
    voice_temperature?: string | null;
    output_audio_format?: "pcm16" | "wav" | "mp3" | "opus";
    telephony_codec?: "pcmu" | "pcma" | "pcm16";
    external_voice_legal_confirmed?: boolean;
    tts_preview_voice?: string | null;
    fallback_voice?: string | null;
    voice_preset?: string | null;
    voice_instructions?: string | null;
    speech_speed?: "slow" | "normal" | "fast";
    pause_style?: "short" | "natural" | "slow";
    phone_reading_style?: "digits" | "groups" | "natural";
    date_reading_style?: "natural" | "numeric";
    price_reading_style?: "brief" | "clear" | "detailed";
    allow_interruptions?: boolean;
    idle_timeout_ms?: number | null;
    ai_disclosure_enabled?: boolean;
    ai_disclosure_message?: string | null;
    preview_audio_format?: "mp3" | "wav" | "opus";
  },
  signal?: AbortSignal,
): Promise<Blob> {
  return apiBlobRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/voice-preview`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    },
  );
}

export interface RealtimePreviewSession {
  id: string;
  call_session_id: string;
  client_secret: string;
  model: string;
  voice: string;
  call_audio_mode: "openai_hosted_sip" | "vps_media_bridge";
  voice_provider: string;
  external_tts_required: boolean;
  initial_message: string;
  expires_at: string;
}

export interface RealtimePreviewToolOutput {
  call_id: string;
  output: Record<string, unknown>;
}

export function createRealtimePreviewSession(
  clinicId: string,
  payload: {
    assistant_config_id?: string | null;
    config: AssistantConfigPayload;
  },
): Promise<RealtimePreviewSession> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/assistant-configs/realtime-preview-sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function heartbeatRealtimePreviewSession(
  sessionId: string,
): Promise<{ ok: boolean; expires_at: string }> {
  return apiRequest(`/api/admin/realtime-preview-sessions/${sessionId}/heartbeat`, {
    method: "POST",
  });
}

export function sendRealtimePreviewToolCall(
  sessionId: string,
  payload: {
    name: string;
    call_id: string;
    arguments: Record<string, unknown>;
  },
): Promise<RealtimePreviewToolOutput> {
  return apiRequest(`/api/admin/realtime-preview-sessions/${sessionId}/tool-call`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function closeRealtimePreviewSession(sessionId: string): Promise<void> {
  return apiRequest(`/api/admin/realtime-preview-sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export function closeRealtimePreviewSessionKeepalive(sessionId: string): void {
  const headers: Record<string, string> = {};
  if (apiConfig.adminApiKey) headers["X-Admin-API-Key"] = apiConfig.adminApiKey;
  void fetch(
    `${apiConfig.baseUrl}/api/admin/realtime-preview-sessions/${sessionId}`,
    {
      method: "DELETE",
      headers,
      keepalive: true,
    },
  ).catch(() => undefined);
}
