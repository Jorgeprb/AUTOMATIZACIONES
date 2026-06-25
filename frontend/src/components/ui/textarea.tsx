import type { TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-24 w-full resize-y rounded-lg border border-[#dfe4ec] bg-white px-3 py-2 text-sm text-[#172033] outline-none transition placeholder:text-[#9aa3b2] focus:border-[#6f8cff] focus:ring-3 focus:ring-[#315efb]/10",
        className,
      )}
      {...props}
    />
  );
}
