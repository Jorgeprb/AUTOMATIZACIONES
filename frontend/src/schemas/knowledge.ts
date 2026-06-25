import { z } from "zod";

import type { KnowledgeCategory } from "@/schemas/domain";

export const knowledgeCategoryLabels: Record<KnowledgeCategory, string> = {
  prices: "Precios",
  services: "Servicios",
  faq: "FAQ",
  policy: "Política",
  location: "Ubicación",
  insurance: "Seguros",
  custom: "Personalizado",
};

export const knowledgeFormSchema = z.object({
  title: z.string().trim().min(1, "El título es obligatorio").max(240),
  category: z.enum([
    "prices",
    "services",
    "faq",
    "policy",
    "location",
    "insurance",
    "custom",
  ]),
  content: z.string().trim().min(1, "El contenido es obligatorio"),
  priority: z.number().int(),
  is_active: z.boolean(),
});

export type KnowledgeFormValues = z.infer<typeof knowledgeFormSchema>;

export const knowledgeDefaults: KnowledgeFormValues = {
  title: "",
  category: "faq",
  content: "",
  priority: 0,
  is_active: true,
};
