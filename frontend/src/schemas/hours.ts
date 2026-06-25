import { z } from "zod";

export const weekdayKeys = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

export type Weekday = (typeof weekdayKeys)[number];
export interface TimeRangeValue {
  start: string;
  end: string;
}
export type WeeklyHours = Record<Weekday, TimeRangeValue[]>;

export const weekdayLabels: Record<Weekday, string> = {
  monday: "Lunes",
  tuesday: "Martes",
  wednesday: "Miércoles",
  thursday: "Jueves",
  friday: "Viernes",
  saturday: "Sábado",
  sunday: "Domingo",
};

const timeSchema = z
  .string()
  .regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Usa formato HH:mm");

export const timeRangeSchema = z
  .object({
    start: timeSchema,
    end: timeSchema,
  })
  .refine((range) => range.end > range.start, {
    message: "La hora final debe ser posterior a la inicial",
    path: ["end"],
  });

export const weeklyHoursSchema = z.object({
  monday: z.array(timeRangeSchema),
  tuesday: z.array(timeRangeSchema),
  wednesday: z.array(timeRangeSchema),
  thursday: z.array(timeRangeSchema),
  friday: z.array(timeRangeSchema),
  saturday: z.array(timeRangeSchema),
  sunday: z.array(timeRangeSchema),
});

export const emptyWeeklyHours: WeeklyHours = {
  monday: [],
  tuesday: [],
  wednesday: [],
  thursday: [],
  friday: [],
  saturday: [],
  sunday: [],
};

export const defaultWeeklyHours: WeeklyHours = {
  monday: [{ start: "09:00", end: "17:00" }],
  tuesday: [{ start: "09:00", end: "17:00" }],
  wednesday: [{ start: "09:00", end: "17:00" }],
  thursday: [{ start: "09:00", end: "17:00" }],
  friday: [{ start: "09:00", end: "17:00" }],
  saturday: [],
  sunday: [],
};

export function normalizeWeeklyHours(value: unknown): WeeklyHours {
  const result: WeeklyHours = structuredClone(emptyWeeklyHours);
  if (!value || typeof value !== "object") return result;
  const source = value as Record<string, unknown>;
  for (const day of weekdayKeys) {
    const ranges = source[day];
    if (!Array.isArray(ranges)) continue;
    result[day] = ranges
      .filter(
        (range): range is { start: string; end: string } =>
          Boolean(
            range &&
              typeof range === "object" &&
              typeof (range as Record<string, unknown>).start === "string" &&
              typeof (range as Record<string, unknown>).end === "string",
          ),
      )
      .map((range) => ({ start: range.start, end: range.end }));
  }
  return result;
}
