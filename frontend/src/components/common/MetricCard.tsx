import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";

export function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
  accent = "blue",
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint?: string;
  accent?: "blue" | "green" | "amber" | "violet";
}) {
  const accents = {
    blue: "bg-[#edf2ff] text-[#315efb]",
    green: "bg-[#e9f8ef] text-[#24804a]",
    amber: "bg-[#fff4df] text-[#ad7111]",
    violet: "bg-[#f2edff] text-[#7650c8]",
  };
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-[#718096]">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-[#19243b]">
            {value}
          </p>
          {hint ? <p className="mt-2 text-xs text-[#8791a2]">{hint}</p> : null}
        </div>
        <div className={`grid size-10 place-items-center rounded-xl ${accents[accent]}`}>
          <Icon className="size-5" />
        </div>
      </div>
    </Card>
  );
}
