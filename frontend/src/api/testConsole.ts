import { apiRequest } from "@/api/client";
import type { TestSession } from "@/schemas/domain";

export interface StartTestSessionPayload {
  assistant_config_id: string;
  use_real_calendar: boolean;
  engine: "simulator" | "openai";
}

export function startTestSession(
  clinicId: string,
  payload: StartTestSessionPayload,
): Promise<TestSession> {
  return apiRequest(`/api/admin/clinics/${clinicId}/test-sessions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function sendTestMessage(
  sessionId: string,
  message: string,
): Promise<TestSession> {
  return apiRequest(`/api/admin/test-sessions/${sessionId}/message`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function getTestSession(sessionId: string): Promise<TestSession> {
  return apiRequest(`/api/admin/test-sessions/${sessionId}`);
}

export function deleteTestSession(
  sessionId: string,
): Promise<{ id: string; status: string }> {
  return apiRequest(`/api/admin/test-sessions/${sessionId}`, {
    method: "DELETE",
  });
}
