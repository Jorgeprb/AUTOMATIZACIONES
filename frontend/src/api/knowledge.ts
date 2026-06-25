import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  KnowledgeCategory,
  KnowledgeItem,
  PromptContextPreviewData,
} from "@/schemas/domain";
import type { KnowledgeFormValues } from "@/schemas/knowledge";

export function listKnowledge(
  clinicId: string,
  params: {
    isActive?: boolean;
    category?: KnowledgeCategory;
    q?: string;
  } = {},
): Promise<Page<KnowledgeItem>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/knowledge${toQuery({
      page: 1,
      page_size: 100,
      is_active: params.isActive,
      category: params.category,
      q: params.q,
    })}`,
  );
}

export function createKnowledge(
  clinicId: string,
  payload: KnowledgeFormValues,
): Promise<KnowledgeItem> {
  return apiRequest(`/api/admin/clinics/${clinicId}/knowledge`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateKnowledge(
  clinicId: string,
  itemId: string,
  payload: Partial<KnowledgeFormValues>,
): Promise<KnowledgeItem> {
  return apiRequest(`/api/admin/clinics/${clinicId}/knowledge/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteKnowledge(
  clinicId: string,
  itemId: string,
): Promise<{ id: string }> {
  return apiRequest(`/api/admin/clinics/${clinicId}/knowledge/${itemId}`, {
    method: "DELETE",
  });
}

export function getPromptContextPreview(
  clinicId: string,
): Promise<PromptContextPreviewData> {
  return apiRequest(`/api/admin/clinics/${clinicId}/prompt-context-preview`);
}
