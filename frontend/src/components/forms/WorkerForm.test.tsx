import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkerForm } from "@/components/forms/WorkerForm";
import { workerDefaults } from "@/schemas/worker";

describe("WorkerForm", () => {
  it("renders and submits an edited weekly schedule", async () => {
    const onSubmit = vi.fn();
    render(
      <WorkerForm
        defaultValues={{
          ...workerDefaults,
          name: "Ana",
          role: "Doctora",
          inherit_clinic_hours: false,
        }}
        clinicHours={workerDefaults.working_hours_json}
        onSubmit={onSubmit}
        onCancel={() => undefined}
        isPending={false}
        submitLabel="Guardar"
      />,
    );

    fireEvent.change(screen.getByLabelText("Lunes fin 1"), {
      target: { value: "18:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit.mock.calls[0]?.[0].working_hours_json.monday[0].end).toBe(
      "18:00",
    );
  });
});
