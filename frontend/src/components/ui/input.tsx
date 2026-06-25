import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Input({
  className,
  type,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "h-10 w-full rounded-lg border border-[#dfe4ec] bg-white px-3 text-sm text-[#172033] outline-none transition placeholder:text-[#9aa3b2] focus:border-[#6f8cff] focus:ring-3 focus:ring-[#315efb]/10 disabled:bg-[#f2f4f7]",
        className,
      )}
      {...props}
    />
  );
}
