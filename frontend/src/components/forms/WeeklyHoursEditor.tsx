import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  type WeeklyHours,
  type Weekday,
  weekdayKeys,
  weekdayLabels,
  weeklyHoursSchema,
} from "@/schemas/hours";

export function WeeklyHoursEditor({
  value,
  onChange,
  error,
}: {
  value: WeeklyHours;
  onChange: (value: WeeklyHours) => void;
  error?: string;
}) {
  const updateDay = (day: Weekday, ranges: WeeklyHours[Weekday]) => {
    onChange({ ...value, [day]: ranges });
  };
  const validation = weeklyHoursSchema.safeParse(value);

  return (
    <div className="space-y-3" data-testid="weekly-hours-editor">
      {weekdayKeys.map((day) => {
        const ranges = value[day];
        return (
          <div
            key={day}
            className="grid gap-3 rounded-xl border border-[#e5e9f0] bg-[#fbfcfe] p-3 md:grid-cols-[100px_1fr]"
          >
            <div>
              <p className="text-sm font-semibold text-[#344158]">
                {weekdayLabels[day]}
              </p>
              <p className="mt-0.5 text-xs text-[#8993a4]">
                {ranges.length ? `${ranges.length} tramo(s)` : "Cerrado"}
              </p>
            </div>
            <div className="space-y-2">
              {ranges.map((range, index) => {
                const invalid = range.end <= range.start;
                return (
                  <div key={`${day}-${index}`} className="flex flex-wrap gap-2">
                    <Input
                      aria-label={`${weekdayLabels[day]} inicio ${index + 1}`}
                      type="time"
                      className="w-32"
                      value={range.start}
                      onChange={(event) => {
                        const next = [...ranges];
                        next[index] = { ...range, start: event.target.value };
                        updateDay(day, next);
                      }}
                    />
                    <Input
                      aria-label={`${weekdayLabels[day]} fin ${index + 1}`}
                      type="time"
                      className={`w-32 ${invalid ? "border-[#d54855]" : ""}`}
                      value={range.end}
                      onChange={(event) => {
                        const next = [...ranges];
                        next[index] = { ...range, end: event.target.value };
                        updateDay(day, next);
                      }}
                    />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      title="Eliminar tramo"
                      onClick={() =>
                        updateDay(
                          day,
                          ranges.filter((_, rangeIndex) => rangeIndex !== index),
                        )
                      }
                    >
                      <Trash2 className="size-4 text-[#bd3341]" />
                    </Button>
                    {invalid ? (
                      <p className="w-full text-xs font-medium text-[#bd3341]">
                        La hora final debe ser posterior a la inicial.
                      </p>
                    ) : null}
                  </div>
                );
              })}
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  updateDay(day, [...ranges, { start: "09:00", end: "14:00" }])
                }
              >
                <Plus className="size-4" />
                Añadir tramo
              </Button>
            </div>
          </div>
        );
      })}
      {!validation.success || error ? (
        <p className="text-xs font-medium text-[#bd3341]">
          {error || "Revisa los tramos horarios marcados."}
        </p>
      ) : null}
    </div>
  );
}
