import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { WeeklyHoursEditor } from "@/components/forms/WeeklyHoursEditor";
import {
  defaultWeeklyHours,
  type WeeklyHours,
  weeklyHoursSchema,
} from "@/schemas/hours";

function Harness() {
  const [hours, setHours] = useState<WeeklyHours>(defaultWeeklyHours);
  return <WeeklyHoursEditor value={hours} onChange={setHours} />;
}

describe("WeeklyHoursEditor", () => {
  it("renders all days and allows a closed day", () => {
    render(<Harness />);
    expect(screen.getByText("Lunes")).toBeInTheDocument();
    expect(screen.getByText("Domingo")).toBeInTheDocument();
    expect(screen.getAllByText("Cerrado")).toHaveLength(2);
  });

  it("rejects ranges whose end is not after start", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Lunes fin 1"), {
      target: { value: "08:00" },
    });
    expect(
      screen.getByText("La hora final debe ser posterior a la inicial."),
    ).toBeInTheDocument();
    expect(
      weeklyHoursSchema.safeParse({
        ...defaultWeeklyHours,
        monday: [{ start: "09:00", end: "08:00" }],
      }).success,
    ).toBe(false);
  });
});
