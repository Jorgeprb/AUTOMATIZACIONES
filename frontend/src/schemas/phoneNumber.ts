import { z } from "zod";

export const phoneNumberFormSchema = z.object({
  provider: z.enum(["voipstudio", "twilio", "other"]),
  phone_number: z.string().trim().min(3, "El número es obligatorio").max(32),
  label: z.string().trim().min(1, "La etiqueta es obligatoria").max(120),
  sip_target: z.string().trim().max(500).optional().or(z.literal("")),
  webhook_url: z
    .string()
    .trim()
    .url("Introduce una URL válida")
    .optional()
    .or(z.literal("")),
  is_active: z.boolean(),
  notes: z.string().trim().optional().or(z.literal("")),
});

export type PhoneNumberFormValues = z.infer<typeof phoneNumberFormSchema>;

export interface PhoneNumber {
  id: string;
  clinic_id: string;
  provider: PhoneNumberFormValues["provider"];
  phone_number: string;
  label: string;
  sip_target: string | null;
  webhook_url: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhoneNumberPayload {
  provider: PhoneNumberFormValues["provider"];
  phone_number: string;
  label: string;
  sip_target: string | null;
  webhook_url: string | null;
  is_active: boolean;
  notes: string | null;
}

export const phoneNumberDefaults: PhoneNumberFormValues = {
  provider: "voipstudio",
  phone_number: "",
  label: "Recepción",
  sip_target: "",
  webhook_url: "",
  is_active: true,
  notes: "",
};
