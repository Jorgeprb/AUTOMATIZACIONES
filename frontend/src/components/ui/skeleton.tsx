import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg bg-gradient-to-r from-[#edf0f4] via-[#f6f7f9] to-[#edf0f4]",
        className,
      )}
    />
  );
}
