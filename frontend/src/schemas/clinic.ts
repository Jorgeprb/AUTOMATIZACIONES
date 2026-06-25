import { z } from "zod";

import {
  defaultWeeklyHours,
  type WeeklyHours,
  weeklyHoursSchema,
} from "@/schemas/hours";

export const clinicFormSchema = z.object({
  name: z.string().trim().min(1, "El nombre es obligatorio").max(200),
  legal_name: z.string().trim().max(240).optional().or(z.literal("")),
  timezone: z.string().trim().min(1, "La zona horaria es obligatoria").max(64),
  default_language: z.string().trim().min(2).max(16),
  main_phone_number: z
    .string()
    .trim()
    .min(3, "El teléfono es obligatorio")
    .max(32),
  address: z.string().trim().optional().or(z.literal("")),
  website: z
    .string()
    .trim()
    .url("Introduce una URL válida")
    .optional()
    .or(z.literal("")),
  email: z
    .string()
    .trim()
    .email("Introduce un email válido")
    .optional()
    .or(z.literal("")),
  description: z.string().trim().optional().or(z.literal("")),
  emergency_message: z.string().trim().optional().or(z.literal("")),
  opening_hours_json: weeklyHoursSchema,
  data_retention_days: z.number().int().min(1).max(3650),
  is_active: z.boolean(),
});

export type ClinicFormValues = z.infer<typeof clinicFormSchema>;

export interface Clinic extends ClinicFormValues {
  id: string;
  created_at: string;
  updated_at: string;
}

export type ClinicPayload = Omit<
  ClinicFormValues,
  "legal_name" | "address" | "website" | "email" | "description" | "emergency_message"
> & {
  legal_name: string | null;
  address: string | null;
  website: string | null;
  email: string | null;
  description: string | null;
  emergency_message: string | null;
  opening_hours_json: WeeklyHours;
};

export const clinicDefaults: ClinicFormValues = {
  name: "",
  legal_name: "",
  timezone: "Europe/Madrid",
  default_language: "es",
  main_phone_number: "",
  address: "",
  website: "",
  email: "",
  description: "",
  emergency_message:
    "Si existe una urgencia médica, llama al 112 o acude a urgencias.",
  opening_hours_json: defaultWeeklyHours,
  data_retention_days: 30,
  is_active: true,
};
