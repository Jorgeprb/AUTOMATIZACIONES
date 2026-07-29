import { z } from "zod";

import {
  defaultWeeklyHours,
  type WeeklyHours,
  weeklyHoursSchema,
} from "@/schemas/hours";

export const workerFormSchema = z.object({
  name: z.string().trim().min(1, "El nombre es obligatorio").max(200),
  role: z.string().trim().min(1, "El rol es obligatorio").max(120),
  public_description: z.string().trim().optional().or(z.literal("")),
  email: z
    .string()
    .trim()
    .email("Introduce un email válido")
    .optional()
    .or(z.literal("")),
  phone_extension: z.string().trim().max(32).optional().or(z.literal("")),
  calendar_id: z.string().trim().max(320).optional().or(z.literal("")),
  color_id: z.string().trim().max(32).optional().or(z.literal("")),
  is_active: z.boolean(),
  inherit_clinic_hours: z.boolean(),
  working_hours_json: weeklyHoursSchema,
});

export type WorkerFormValues = z.infer<typeof workerFormSchema>;
export interface WorkerPayload {
  name: string;
  role: string;
  public_description: string | null;
  email: string | null;
  phone_extension: string | null;
  calendar_id: string | null;
  color_id: string | null;
  is_active: boolean;
  inherit_clinic_hours: boolean;
  working_hours_json: WeeklyHours;
}

export const workerDefaults: WorkerFormValues = {
  name: "",
  role: "",
  public_description: "",
  email: "",
  phone_extension: "",
  calendar_id: "",
  color_id: "",
  is_active: true,
  inherit_clinic_hours: true,
  working_hours_json: defaultWeeklyHours,
};
