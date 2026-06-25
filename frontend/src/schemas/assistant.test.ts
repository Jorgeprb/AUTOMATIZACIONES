import { describe, expect, it } from "vitest";

import {
  applyAssistantTemplate,
  assistantConfigDefaults,
  assistantConfigFormSchema,
} from "@/schemas/assistant";

describe("assistant configuration", () => {
  it("validates required prompt fields", () => {
    expect(
      assistantConfigFormSchema.safeParse({
        ...assistantConfigDefaults,
        first_message: "",
        system_prompt: "",
      }).success,
    ).toBe(false);
  });

  it("applies a template without overwriting operational data", () => {
    const current = {
      ...assistantConfigDefaults,
      name: "Mi configuración",
      realtime_model: "modelo-local",
      realtime_voice: "cedar",
      transcript_enabled: true,
      recording_enabled: true,
      conversation_retention_days: 90,
    };
    const result = applyAssistantTemplate(current, "Fisioterapia");

    expect(result.first_message).toContain("fisioterapia");
    expect(result.name).toBe("Mi configuración");
    expect(result.realtime_model).toBe("modelo-local");
    expect(result.realtime_voice).toBe("cedar");
    expect(result.transcript_enabled).toBe(true);
    expect(result.recording_enabled).toBe(true);
    expect(result.conversation_retention_days).toBe(90);
  });
});
