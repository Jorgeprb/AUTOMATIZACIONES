import { describe, expect, it } from "vitest";

import {
  applyAssistantTemplate,
  applyVoicePreset,
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
    expect(result.tone).toBe("cercano");
    expect(result.response_length).toBe("normal");
    expect(result.no_availability_message).toContain("huecos");
  });

  it("validates behavior fields and prompt length", () => {
    const valid = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      tone: "comercial",
      response_length: "corta",
      max_proposed_slots: 3,
    });
    const invalid = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      max_proposed_slots: 0,
      system_prompt: "x".repeat(12001),
    });

    expect(valid.success).toBe(true);
    expect(invalid.success).toBe(false);
  });

  it("validates and applies voice profile presets", () => {
    const current = {
      ...assistantConfigDefaults,
      realtime_voice: "marin",
      tts_preview_voice: "cedar",
      idle_timeout_ms: "5000",
    };
    const result = applyVoicePreset(current, "Centralita breve");
    const invalidTimeout = assistantConfigFormSchema.safeParse({
      ...result,
      idle_timeout_ms: "10",
    });

    expect(result.voice_preset).toBe("Centralita breve");
    expect(result.speech_speed).toBe("fast");
    expect(result.phone_reading_style).toBe("digits");
    expect(result.realtime_voice).toBe("marin");
    expect(result.tts_preview_voice).toBe("cedar");
    expect(assistantConfigFormSchema.safeParse(result).success).toBe(true);
    expect(invalidTimeout.success).toBe(false);
  });

  it("validates dual call audio mode for external voices", () => {
    const invalidHostedExternal = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      voice_provider: "azure",
      call_audio_mode: "openai_hosted_sip",
    });
    const validBridgeExternal = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      voice_provider: "azure",
      call_audio_mode: "vps_media_bridge",
      voice_id: "es-ES-ElviraNeural",
    });
    const customWithoutLegal = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      voice_provider: "elevenlabs",
      call_audio_mode: "vps_media_bridge",
      voice_id: "custom_voice",
      external_voice_legal_confirmed: false,
    });
    const customWithLegal = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      voice_provider: "elevenlabs",
      call_audio_mode: "vps_media_bridge",
      voice_id: "custom_voice",
      external_voice_legal_confirmed: true,
    });

    expect(invalidHostedExternal.success).toBe(false);
    expect(validBridgeExternal.success).toBe(true);
    expect(customWithoutLegal.success).toBe(false);
    expect(customWithLegal.success).toBe(true);
  });

  it("accepts Azure Sabela with VPS media bridge and PCMA", () => {
    const sabela = assistantConfigFormSchema.safeParse({
      ...assistantConfigDefaults,
      call_audio_mode: "vps_media_bridge",
      voice_provider: "azure",
      tts_model: "azure-neural",
      voice_id: "gl-ES-SabelaNeural",
      voice_locale: "gl-ES",
      azure_speech_region: "westeurope",
      telephony_codec: "pcma",
    });

    expect(sabela.success).toBe(true);
  });
});
