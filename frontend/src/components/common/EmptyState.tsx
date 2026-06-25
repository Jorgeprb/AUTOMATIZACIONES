import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-[#d9dee7] bg-white px-6 text-center">
      <div className="mb-4 grid size-11 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
        <Icon className="size-5" />
      </div>
      <h3 className="font-semibold text-[#1d2940]">{title}</h3>
      <p className="mt-1 max-w-md text-sm leading-6 text-[#738096]">
        {description}
      </p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
