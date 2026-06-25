import type { ReactNode } from "react";

export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="grid gap-5 border-b border-[#edf0f4] pb-6 last:border-0 last:pb-0 md:grid-cols-[180px_1fr]">
      <div>
        <h3 className="text-sm font-semibold text-[#27334a]">{title}</h3>
        {description ? (
          <p className="mt-1 text-xs leading-5 text-[#7a8598]">{description}</p>
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}
