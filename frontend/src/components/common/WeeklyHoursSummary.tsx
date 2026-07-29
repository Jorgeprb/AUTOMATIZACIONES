import {
  type WeeklyHours,
  weekdayKeys,
  weekdayLabels,
} from "@/schemas/hours";
import { cn } from "@/lib/utils";

export function WeeklyHoursSummary({
  value,
  compact = false,
}: {
  value: WeeklyHours;
  compact?: boolean;
}) {
  return (
    <div className={cn("grid gap-2", compact ? "sm:grid-cols-2" : "lg:grid-cols-2")}>
      {weekdayKeys.map((day) => {
        const ranges = value[day];
        return (
          <div
            key={day}
            className="flex items-start justify-between gap-4 rounded-lg border border-[#e8ebf0] bg-white px-3 py-2.5"
          >
            <span className="text-sm font-semibold text-[#354158]">
              {weekdayLabels[day]}
            </span>
            <span className="text-right text-sm text-[#68758a]">
              {ranges.length
                ? ranges.map((range) => `${range.start}–${range.end}`).join(", ")
                : "Cerrado"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
