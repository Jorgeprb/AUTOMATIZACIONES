import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  KnowledgeCategory,
  KnowledgeImportPreview,
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

export function previewPdfKnowledge(
  clinicId: string,
  values: {
    file: File;
    category: KnowledgeCategory;
  },
): Promise<KnowledgeImportPreview> {
  const data = new FormData();
  data.set("file", values.file);
  data.set("category", values.category);
  return apiRequest(
    `/api/admin/clinics/${clinicId}/knowledge/import/pdf/preview`,
    {
      method: "POST",
      body: data,
    },
  );
}

export function importPdfKnowledge(
  clinicId: string,
  values: {
    file: File;
    title?: string;
    category: KnowledgeCategory;
    priority: number;
    is_active: boolean;
  },
): Promise<KnowledgeItem> {
  const data = new FormData();
  data.set("file", values.file);
  data.set("category", values.category);
  data.set("priority", String(values.priority));
  data.set("is_active", String(values.is_active));
  if (values.title) data.set("title", values.title);
  return apiRequest(`/api/admin/clinics/${clinicId}/knowledge/import/pdf`, {
    method: "POST",
    body: data,
  });
}

export function previewUrlKnowledge(
  clinicId: string,
  values: {
    url: string;
    title?: string;
    category: KnowledgeCategory;
    priority?: number;
    is_active?: boolean;
  },
): Promise<KnowledgeImportPreview> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/knowledge/import/url/preview`,
    {
      method: "POST",
      body: JSON.stringify(values),
    },
  );
}

export function importUrlKnowledge(
  clinicId: string,
  values: {
    url: string;
    title?: string;
    category: KnowledgeCategory;
    priority: number;
    is_active: boolean;
  },
): Promise<KnowledgeItem> {
  return apiRequest(`/api/admin/clinics/${clinicId}/knowledge/import/url`, {
    method: "POST",
    body: JSON.stringify(values),
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
