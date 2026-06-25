import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  AssistantConfig,
  AssistantOptions,
  PromptPreview,
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
