import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getGoogleOAuthDiagnostics,
  getGoogleOAuthStartUrl,
  linkWorkerCalendar,
} from "@/api/calendar";
import { apiBlobRequest, apiRequest, toQuery } from "@/api/client";
import {
  activateAssistantConfig,
  previewAssistantVoice,
} from "@/api/assistants";
import { cancelAppointment } from "@/api/appointments";
import {
  anonymizeCallPhone,
  deleteCallContent,
  getCallDebug,
  listCalls,
} from "@/api/calls";
import {
  createKnowledge,
  importPdfKnowledge,
  importUrlKnowledge,
  previewPdfKnowledge,
  previewUrlKnowledge,
} from "@/api/knowledge";
import { createService } from "@/api/services";
import { createWorker } from "@/api/workers";
import {
  getClinicDashboard,
  getSetupStatus,
} from "@/api/dashboard";
import {
  closeTestSession,
  deleteTestSession,
  sendTestMessage,
  startTestSession,
  synthesizeTestSessionAudio,
} from "@/api/testConsole";
import {
  createFlow,
  listFlowTemplates,
  previewFlowPrompt,
} from "@/api/flows";
import { defaultWeeklyHours } from "@/schemas/hours";

vi.mock("@/api/client", () => ({
  apiBlobRequest: vi.fn(),
  apiRequest: vi.fn(),
  toQuery: vi.fn(() => ""),
}));

describe("operational API calls", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
    vi.mocked(apiBlobRequest).mockReset();
  });

  it("creates a worker with weekly hours", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "worker-1" });
    await createWorker("clinic-1", {
      name: "Ana",
      role: "Doctora",
      public_description: null,
      email: null,
      phone_extension: null,
      calendar_id: null,
      color_id: null,
      is_active: true,
      working_hours_json: defaultWeeklyHours,
    });
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/workers",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(vi.mocked(apiRequest).mock.calls[0]?.[1]?.body as string))
      .toMatchObject({ name: "Ana", working_hours_json: defaultWeeklyHours });
  });

  it("links an existing calendar and color", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ worker_id: "worker-1" });
    await linkWorkerCalendar("clinic-1", "worker-1", {
      calendar_id: "ana@example.com",
      color_id: "7",
    });
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/workers/worker-1/link-calendar",
      {
        method: "POST",
        body: JSON.stringify({
          calendar_id: "ana@example.com",
          color_id: "7",
        }),
      },
    );
  });

  it("loads Google OAuth diagnostics and safe start URL", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ configured: false });
    await getGoogleOAuthDiagnostics("clinic-1");
    await getGoogleOAuthStartUrl("clinic-1");
    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/google-oauth/diagnostics",
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/google-oauth/start-url",
    );
  });

  it("creates services and knowledge through the admin API", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "created" });
    await createService("clinic-1", {
      name: "consulta",
      public_name: "Consulta",
      description: null,
      price_text: "50 €",
      price_amount: null,
      currency: "EUR",
      duration_minutes: 30,
      buffer_before_minutes: 5,
      buffer_after_minutes: 5,
      requires_worker: true,
      allowed_worker_ids: ["worker-1"],
      is_bookable_by_bot: true,
      is_active: true,
    });
    await createKnowledge("clinic-1", {
      title: "Política de cancelación",
      category: "policy",
      content: "Avisar con 24 horas.",
      priority: 50,
      is_active: true,
    });

    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/services",
      expect.objectContaining({ method: "POST" }),
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/knowledge",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("previews and imports PDF/URL knowledge", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "knowledge-1" });
    const file = new File(["pdf"], "tarifas.pdf", { type: "application/pdf" });
    await previewPdfKnowledge("clinic-1", {
      file,
      category: "prices",
    });
    await importPdfKnowledge("clinic-1", {
      file,
      title: "Tarifas",
      category: "prices",
      priority: 80,
      is_active: true,
    });
    await previewUrlKnowledge("clinic-1", {
      url: "https://example.test/faq",
      category: "faq",
    });
    await importUrlKnowledge("clinic-1", {
      url: "https://example.test/faq",
      category: "faq",
      priority: 10,
      is_active: true,
    });

    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/knowledge/import/pdf/preview",
      expect.objectContaining({ method: "POST" }),
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/knowledge/import/pdf",
      expect.objectContaining({ method: "POST" }),
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      3,
      "/api/admin/clinics/clinic-1/knowledge/import/url/preview",
      expect.objectContaining({ method: "POST" }),
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      4,
      "/api/admin/clinics/clinic-1/knowledge/import/url",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("activates the selected assistant configuration", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "config-2", is_active: true });
    await activateAssistantConfig("clinic-1", "config-2");
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/assistant-configs/config-2/activate",
      { method: "POST" },
    );
  });

  it("generates an assistant voice preview as audio", async () => {
    vi.mocked(apiBlobRequest).mockResolvedValue(new Blob(["mp3"]));
    const signal = new AbortController().signal;
    await previewAssistantVoice(
      "clinic-1",
      {
        text: "Hola, soy el asistente.",
        realtime_voice: "marin",
        realtime_model: "gpt-realtime-2",
      },
      signal,
    );
    expect(apiBlobRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/assistant-configs/voice-preview",
      {
        method: "POST",
        body: JSON.stringify({
          text: "Hola, soy el asistente.",
          realtime_voice: "marin",
          realtime_model: "gpt-realtime-2",
        }),
        signal,
      },
    );
  });

  it("lists calls with analysis filters", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 0 });
    await listCalls("clinic-1", {
      outcome: "appointment_created",
      workerId: "worker-1",
      phone: "+34600",
    });
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/calls",
    );
    expect(vi.mocked(toQuery)).toHaveBeenCalledWith(
      expect.objectContaining({
        outcome: "appointment_created",
        worker_id: "worker-1",
        phone: "+34600",
      }),
    );
  });

  it("uses privacy, debug, and appointment cancellation endpoints", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ status: "ok" });
    await deleteCallContent("clinic-1", "call-1");
    await anonymizeCallPhone("clinic-1", "call-1");
    await getCallDebug("clinic-1", "call-1");
    await cancelAppointment("clinic-1", "appointment-1");

    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/calls/call-1/content",
      { method: "DELETE" },
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/calls/call-1/anonymize-phone",
      { method: "POST" },
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      3,
      "/api/admin/clinics/clinic-1/calls/call-1/debug",
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      4,
      "/api/admin/clinics/clinic-1/appointments/appointment-1/cancel",
      { method: "POST" },
    );
  });

  it("starts, advances, and resets browser test sessions", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "session-1" });
    await startTestSession("clinic-1", {
      assistant_config_id: "config-1",
      use_real_calendar: false,
      engine: "simulator",
    });
    await sendTestMessage("session-1", "Quiero una cita");
    await closeTestSession("session-1");
    await deleteTestSession("session-1");
    vi.mocked(apiBlobRequest).mockResolvedValue(new Blob(["mp3"]));
    await synthesizeTestSessionAudio("session-1", "Hola");

    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/test-sessions",
      {
        method: "POST",
        body: JSON.stringify({
          assistant_config_id: "config-1",
          use_real_calendar: false,
          engine: "simulator",
        }),
      },
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/test-sessions/session-1/message",
      {
        method: "POST",
        body: JSON.stringify({ message: "Quiero una cita" }),
      },
      );
      expect(apiRequest).toHaveBeenNthCalledWith(
        3,
        "/api/admin/test-sessions/session-1/close",
        { method: "POST" },
      );
      expect(apiRequest).toHaveBeenNthCalledWith(
        4,
        "/api/admin/test-sessions/session-1",
        { method: "DELETE" },
      );
      expect(apiBlobRequest).toHaveBeenCalledWith(
        "/api/admin/test-sessions/session-1/tts",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ text: "Hola" }),
        }),
      );
  });

  it("loads clinic dashboard and production checklist", async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await getClinicDashboard("clinic-1");
    await getSetupStatus("clinic-1");
    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/dashboard",
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/setup-status",
    );
  });

  it("creates and previews configurable conversation flows", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "flow-1" });
    await listFlowTemplates("clinic-1");
    await createFlow("clinic-1", {
      name: "Reserva estándar",
      description: null,
      is_active: true,
      flow_json: {
        name: "Reserva estándar",
        steps: [
          {
            id: "propose",
            type: "tool",
            tool_name: "propose_slots",
          },
        ],
      },
    });
    await previewFlowPrompt("clinic-1", "flow-1", "config-1");

    expect(apiRequest).toHaveBeenNthCalledWith(
      1,
      "/api/admin/clinics/clinic-1/flow-templates",
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      2,
      "/api/admin/clinics/clinic-1/flows",
      expect.objectContaining({ method: "POST" }),
    );
    expect(apiRequest).toHaveBeenNthCalledWith(
      3,
      "/api/admin/clinics/clinic-1/flows/flow-1/preview-prompt",
      { method: "POST" },
    );
    expect(vi.mocked(toQuery)).toHaveBeenCalledWith({
      config_id: "config-1",
    });
  });
});
