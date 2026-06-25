import { Circle } from "lucide-react";

import { Badge } from "@/components/ui/badge";

type Status = "success" | "warning" | "danger" | "neutral" | "info";

export function StatusBadge({
  status,
  children,
}: {
  status: Status;
  children: string;
}) {
  const variant =
    status === "success"
      ? "success"
      : status === "warning"
        ? "warning"
        : status === "danger"
          ? "danger"
          : status === "neutral"
            ? "neutral"
            : "default";
  return (
    <Badge variant={variant}>
      <Circle className="size-1.5 fill-current" />
      {children}
    </Badge>
  );
}
