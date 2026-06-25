import { describe, expect, it } from "vitest";

import { conversationFlowDefinitionSchema } from "@/schemas/flow";

describe("conversationFlowDefinitionSchema", () => {
  it("accepts the standard booking structure", () => {
    const result = conversationFlowDefinitionSchema.safeParse({
      name: "Reserva estándar",
      steps: [
        {
          id: "collect_patient_name",
          type: "collect",
          field: "patient_name",
          required: true,
        },
        {
          id: "propose_slots",
          type: "tool",
          tool_name: "propose_slots",
        },
        {
          id: "confirm",
          type: "confirmation",
          required: true,
        },
        {
          id: "create",
          type: "tool",
          tool_name: "create_appointment",
        },
      ],
    });
    expect(result.success).toBe(true);
  });

  it("rejects unknown tools and invalid fields", () => {
    expect(
      conversationFlowDefinitionSchema.safeParse({
        name: "Inválido",
        steps: [{ id: "bad", type: "tool", tool_name: "invented_tool" }],
      }).success,
    ).toBe(false);
    expect(
      conversationFlowDefinitionSchema.safeParse({
        name: "Inválido",
        steps: [{ id: "bad", type: "collect", field: "medical_history" }],
      }).success,
    ).toBe(false);
  });
});
