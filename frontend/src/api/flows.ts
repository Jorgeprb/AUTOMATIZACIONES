import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  ConversationFlow,
  ConversationFlowDefinition,
  ConversationFlowTemplate,
  PromptPreview,
} from "@/schemas/domain";

export interface ConversationFlowPayload {
  name: string;
  description: string | null;
  flow_json: ConversationFlowDefinition;
  is_active: boolean;
}

export function listFlows(clinicId: string): Promise<Page<ConversationFlow>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/flows${toQuery({
      page: 1,
      page_size: 100,
    })}`,
  );
}

export function listFlowTemplates(
  clinicId: string,
): Promise<ConversationFlowTemplate[]> {
  return apiRequest(`/api/admin/clinics/${clinicId}/flow-templates`);
}

export function createFlow(
  clinicId: string,
  payload: ConversationFlowPayload,
): Promise<ConversationFlow> {
  return apiRequest(`/api/admin/clinics/${clinicId}/flows`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateFlow(
  clinicId: string,
  flowId: string,
  payload: Partial<ConversationFlowPayload>,
): Promise<ConversationFlow> {
  return apiRequest(`/api/admin/clinics/${clinicId}/flows/${flowId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteFlow(
  clinicId: string,
  flowId: string,
): Promise<{ id: string }> {
  return apiRequest(`/api/admin/clinics/${clinicId}/flows/${flowId}`, {
    method: "DELETE",
  });
}

export function previewFlowPrompt(
  clinicId: string,
  flowId: string,
  configId: string,
): Promise<PromptPreview> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/flows/${flowId}/preview-prompt${toQuery({
      config_id: configId,
    })}`,
    { method: "POST" },
  );
}
