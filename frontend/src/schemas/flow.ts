import { z } from "zod";

export const flowFields = [
  "intent",
  "patient_name",
  "patient_phone",
  "service",
  "reason",
  "preferred_date",
  "preferred_time_window",
  "worker_preference",
  "appointment_id",
  "approximate_date",
] as const;

export const flowTools = [
  "get_clinic_info",
  "propose_slots",
  "check_availability",
  "create_appointment",
  "cancel_appointment",
  "transfer_to_human",
  "end_call",
] as const;

const baseStep = z.object({
  id: z.string().regex(/^[a-z][a-z0-9_]*$/, "ID de paso inválido"),
});

const messageStep = baseStep.extend({
  type: z.literal("message"),
  text: z.string().trim().min(1),
  required: z.boolean().optional(),
});

const collectStep = baseStep.extend({
  type: z.literal("collect"),
  field: z.enum(flowFields),
  required: z.boolean().optional(),
});

const toolStep = baseStep.extend({
  type: z.literal("tool"),
  tool_name: z.enum(flowTools),
  required: z.boolean().optional(),
});

const confirmationStep = baseStep.extend({
  type: z.literal("confirmation"),
  required: z.boolean().optional(),
});

export const conversationFlowDefinitionSchema = z
  .object({
    name: z.string().trim().min(1).max(200),
    objectives: z.array(z.string().trim().min(1)).max(10).optional(),
    exit_conditions: z.array(z.string().trim().min(1)).max(10).optional(),
    steps: z
      .array(
        z.discriminatedUnion("type", [
          messageStep,
          collectStep,
          toolStep,
          confirmationStep,
        ]),
      )
      .min(1)
      .max(50),
  })
  .superRefine((value, context) => {
    const ids = value.steps.map((step) => step.id);
    if (new Set(ids).size !== ids.length) {
      context.addIssue({
        code: "custom",
        message: "Los IDs de los pasos deben ser únicos",
        path: ["steps"],
      });
    }
  });

export function parseFlowJson(value: string) {
  const parsed: unknown = JSON.parse(value);
  return conversationFlowDefinitionSchema.parse(parsed);
}
