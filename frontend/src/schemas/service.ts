import { z } from "zod";

export const serviceFormSchema = z.object({
  name: z.string().trim().min(1, "El nombre interno es obligatorio").max(200),
  public_name: z
    .string()
    .trim()
    .min(1, "El nombre público es obligatorio")
    .max(200),
  description: z.string().trim().optional().or(z.literal("")),
  aliases_text: z.string().max(3000),
  common_phrases_text: z.string().max(5000),
  keywords_text: z.string().max(3000),
  disambiguation_instructions: z.string().max(5000),
  price_text: z.string().trim().max(200).optional().or(z.literal("")),
  price_amount: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || (Number.isFinite(Number(value)) && Number(value) >= 0),
      "Introduce un precio válido",
    ),
  currency: z.string().trim().length(3, "Usa un código de 3 letras"),
  duration_minutes: z.number().int().positive("La duración debe ser mayor que 0"),
  buffer_before_minutes: z.number().int().min(0),
  buffer_after_minutes: z.number().int().min(0),
  requires_worker: z.boolean(),
  allowed_worker_ids: z.array(z.string()),
  is_bookable_by_bot: z.boolean(),
  is_active: z.boolean(),
});

export type ServiceFormValues = z.infer<typeof serviceFormSchema>;

export interface ServicePayload {
  name: string;
  public_name: string;
  description: string | null;
  aliases_json: string[];
  common_phrases_json: string[];
  keywords_json: string[];
  disambiguation_instructions: string | null;
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
}

export const serviceDefaults: ServiceFormValues = {
  name: "",
  public_name: "",
  description: "",
  aliases_text: "",
  common_phrases_text: "",
  keywords_text: "",
  disambiguation_instructions: "",
  price_text: "",
  price_amount: "",
  currency: "EUR",
  duration_minutes: 30,
  buffer_before_minutes: 0,
  buffer_after_minutes: 0,
  requires_worker: true,
  allowed_worker_ids: [],
  is_bookable_by_bot: true,
  is_active: true,
};
