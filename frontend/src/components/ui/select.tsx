import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 w-full rounded-lg border border-[#dfe4ec] bg-white px-3 text-sm text-[#27334a] outline-none focus:border-[#6f8cff] focus:ring-3 focus:ring-[#315efb]/10",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
