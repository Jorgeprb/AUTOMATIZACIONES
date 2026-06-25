import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
  {
    variants: {
      variant: {
        default: "bg-[#edf2ff] text-[#3654bd]",
        success: "bg-[#e9f8ef] text-[#237a47]",
        warning: "bg-[#fff5df] text-[#996515]",
        danger: "bg-[#ffebee] text-[#b42d3b]",
        neutral: "bg-[#eef1f5] text-[#5f6b7d]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
