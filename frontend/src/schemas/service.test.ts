import { describe, expect, it } from "vitest";

import { serviceDefaults, serviceFormSchema } from "@/schemas/service";

describe("serviceFormSchema", () => {
  it("requires a positive duration", () => {
    expect(
      serviceFormSchema.safeParse({
        ...serviceDefaults,
        name: "consulta",
        public_name: "Consulta",
        duration_minutes: 0,
      }).success,
    ).toBe(false);
  });

  it("allows a missing price because the prompt handles it explicitly", () => {
    expect(
      serviceFormSchema.safeParse({
        ...serviceDefaults,
        name: "consulta",
        public_name: "Consulta",
        price_text: "",
        price_amount: "",
      }).success,
    ).toBe(true);
  });
});
