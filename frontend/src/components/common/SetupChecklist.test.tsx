import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SetupChecklist } from "@/components/common/SetupChecklist";

describe("SetupChecklist", () => {
  it("renders completed and pending automatic steps with links", () => {
    render(
      <MemoryRouter>
        <SetupChecklist
          status={{
            clinic_id: "clinic-1",
            completed: false,
            blocking_errors: ["Google Calendar conectado"],
            warnings: ["Prueba simulada realizada"],
            items: [
              {
                key: "clinic_basics",
                label: "Datos básicos de clínica completos",
                completed: true,
                automatic: true,
                href: "/clinics/clinic-1",
                help: "Completa los datos básicos.",
              },
              {
                key: "google_calendar",
                label: "Google Calendar conectado",
                completed: false,
                automatic: true,
                href: "/clinics/clinic-1/calendar",
                help: "Conecta Google.",
              },
            ],
          }}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByText("Checklist de puesta en producción"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 de 2 pasos completados.")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Google Calendar conectado/ }),
    ).toHaveAttribute("href", "/clinics/clinic-1/calendar");
    expect(screen.getAllByText("Automático")).toHaveLength(2);
    expect(screen.getByText("Bloqueos para producción")).toBeInTheDocument();
  });
});
