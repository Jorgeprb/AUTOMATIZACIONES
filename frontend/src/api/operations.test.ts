import { beforeEach, describe, expect, it, vi } from "vitest";

import { linkWorkerCalendar } from "@/api/calendar";
import { apiRequest, toQuery } from "@/api/client";
import { activateAssistantConfig } from "@/api/assistants";
import { cancelAppointment } from "@/api/appointments";
import {
  anonymizeCallPhone,
  deleteCallContent,
  getCallDebug,
  listCalls,
} from "@/api/calls";
import { createKnowledge } from "@/api/knowledge";
import { createService } from "@/api/services";
import { createWorker } from "@/api/workers";
import {
  getClinicDashboard,
  getSetupStatus,
} from "@/api/dashboard";
import {
  deleteTestSession,
  sendTestMessage,
  startTestSession,
} from "@/api/testConsole";
import {
  createFlow,
  listFlowTemplates,
  previewFlowPrompt,
} from "@/api/flows";
import { defaultWeeklyHours } from "@/schemas/hours";

vi.mock("@/api/client", () => ({
  apiRequest: vi.fn(),
  toQuery: vi.fn(() => ""),
}));

describe("operational API calls", () => {
  beforeEach(() => vi.mocked(apiRequest).mockReset());

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

  it("activates the selected assistant configuration", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ id: "config-2", is_active: true });
    await activateAssistantConfig("clinic-1", "config-2");
    expect(apiRequest).toHaveBeenCalledWith(
      "/api/admin/clinics/clinic-1/assistant-configs/config-2/activate",
      { method: "POST" },
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
    await deleteTestSession("session-1");

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
      "/api/admin/test-sessions/session-1",
      { method: "DELETE" },
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
