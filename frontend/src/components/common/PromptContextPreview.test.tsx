import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { getPromptContextPreview } from "@/api/knowledge";
import { PromptContextPreview } from "@/components/common/PromptContextPreview";

vi.mock("@/api/knowledge", () => ({
  getPromptContextPreview: vi.fn(),
}));
vi.mock("@/api/assistants", () => ({
  previewPrompt: vi.fn(),
}));

describe("PromptContextPreview", () => {
  it("renders effective services, prices, workers, knowledge and warnings", async () => {
    vi.mocked(getPromptContextPreview).mockResolvedValue({
      clinic_id: "clinic-1",
      assistant_config_id: "config-1",
      services: [
        {
          id: "service-1",
          public_name: "Consulta general",
          description: "Consulta de 30 minutos",
          price: "50 €",
          duration_minutes: 30,
          total_duration_minutes: 40,
          requires_worker: true,
          worker_names: ["Ana"],
          is_bookable_by_bot: true,
        },
      ],
      workers: [
        {
          id: "worker-1",
          name: "Ana",
          role: "Médica",
          calendar_linked: true,
        },
      ],
      knowledge_items: [
        {
          id: "knowledge-1",
          title: "Seguro privado",
          category: "insurance",
          content: "Consultar cobertura.",
          priority: 20,
        },
      ],
      warnings: ["Este servicio no tiene precio"],
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <PromptContextPreview clinicId="clinic-1" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Consulta general")).toBeInTheDocument();
    expect(screen.getByText("50 €")).toBeInTheDocument();
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.getByText("Seguro privado")).toBeInTheDocument();
    expect(screen.getByText("Este servicio no tiene precio")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ver prompt final" }),
    ).toBeEnabled();
  });
});
