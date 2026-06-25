import { apiRequest } from "@/api/client";
import type {
  CalendarList,
  CalendarStatus,
  WorkerCalendarResult,
  WorkerFreeBusyResult,
} from "@/schemas/domain";

export function getCalendarStatus(clinicId: string): Promise<CalendarStatus> {
  return apiRequest(`/api/admin/clinics/${clinicId}/calendar-status`);
}

export function listCalendars(clinicId: string): Promise<CalendarList> {
  return apiRequest(`/api/admin/clinics/${clinicId}/calendars`);
}

export function createWorkerCalendar(
  clinicId: string,
  workerId: string,
  payload: { summary?: string; color_id?: string },
): Promise<WorkerCalendarResult> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/workers/${workerId}/create-calendar`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function linkWorkerCalendar(
  clinicId: string,
  workerId: string,
  payload: { calendar_id: string; color_id?: string },
): Promise<WorkerCalendarResult> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/workers/${workerId}/link-calendar`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function testWorkerFreeBusy(
  clinicId: string,
  workerId: string,
  payload: { time_min: string; time_max: string },
): Promise<WorkerFreeBusyResult> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/workers/${workerId}/test-freebusy`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
