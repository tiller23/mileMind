import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlanCalendar } from "@/components/PlanCalendar";
import type { PlanWeek } from "@/lib/types";

const SAMPLE_WEEKS: PlanWeek[] = [
  {
    week_number: 1,
    phase: "base",
    workouts: [
      { day: 1, workout_type: "easy", distance_km: 5, pace_zone: "Zone 2", duration_minutes: 35, intensity: 0.65, tss: 24.65, description: "Zone 2 easy run" },
      { day: 3, workout_type: "rest" },
      { day: 5, workout_type: "long_run", distance_km: 8, pace_zone: "Zone 2", duration_minutes: 55, intensity: 0.68, tss: 42.3, description: "Zone 2 long run" },
    ],
    target_load: 66.95,
    notes: "Base phase week 1",
  },
  {
    week_number: 2,
    phase: "base",
    workouts: [
      { day: 1, workout_type: "easy", distance_km: 5.5, duration_minutes: 38, intensity: 0.65 },
      { day: 3, workout_type: "tempo", distance_km: 4, pace_zone: "Zone 3", duration_minutes: 28, intensity: 0.80, description: "Tempo run" },
      { day: 5, workout_type: "long_run", distance_km: 8.5, duration_minutes: 58, intensity: 0.68 },
      { day: 7, workout_type: "recovery", distance_km: 3, duration_minutes: 25, intensity: 0.55 },
    ],
    notes: "Base phase week 2",
  },
];

describe("PlanCalendar", () => {
  it("renders day headers", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    expect(screen.getByText("Mon")).toBeInTheDocument();
    expect(screen.getByText("Sun")).toBeInTheDocument();
  });

  it("renders week labels", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    expect(screen.getByText("Wk 1")).toBeInTheDocument();
    expect(screen.getByText("Wk 2")).toBeInTheDocument();
  });

  it("renders phase badges", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    const badges = screen.getAllByText("base");
    expect(badges.length).toBe(2);
  });

  it("renders legend", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    // Legend items exist (may also appear in cells)
    expect(screen.getAllByText("Easy Run").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Long Run").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Rest").length).toBeGreaterThanOrEqual(1);
    // Legend-specific items that don't appear as workout types in the data
    expect(screen.getByText("Intervals")).toBeInTheDocument();
    expect(screen.getByText("Hills")).toBeInTheDocument();
  });

  it("renders workout types in cells", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    // "Easy" appears in legend + 2 workout cells
    expect(screen.getAllByText("Easy Run").length).toBeGreaterThanOrEqual(2);
  });

  it("renders workout distances", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    expect(screen.getByText("5 km")).toBeInTheDocument();
    expect(screen.getByText("8 km")).toBeInTheDocument();
  });

  it("shows workout detail on click", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    // Find workout buttons (not legend items) — buttons have distance text
    const cell = screen.getByText("5 km").closest("button");
    expect(cell).not.toBeNull();
    fireEvent.click(cell!);
    expect(screen.getByText("Zone 2 easy run")).toBeInTheDocument();
    expect(screen.getByText("35 min")).toBeInTheDocument();
  });

  it("closes workout detail on close button", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    const cell = screen.getByText("5 km").closest("button");
    fireEvent.click(cell!);
    expect(screen.getByText("Zone 2 easy run")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Close details"));
    expect(screen.queryByText("Zone 2 easy run")).not.toBeInTheDocument();
  });

  it("renders week notes", () => {
    render(<PlanCalendar weeks={SAMPLE_WEEKS} />);
    expect(screen.getByText("Base phase week 1")).toBeInTheDocument();
  });

  it("handles empty weeks array", () => {
    render(<PlanCalendar weeks={[]} />);
    expect(screen.getByText("Mon")).toBeInTheDocument();
  });

  it("handles workouts with missing day field gracefully", () => {
    const weeks: PlanWeek[] = [
      {
        week_number: 1,
        phase: "base",
        workouts: [
          { day: 1, workout_type: "easy", duration_minutes: 30, intensity: 0.65 },
          { workout_type: "tempo", duration_minutes: 20, intensity: 0.80 } as PlanWeek["workouts"][0],
        ],
      },
    ];
    render(<PlanCalendar weeks={weeks} />);
    expect(screen.getByText("Wk 1")).toBeInTheDocument();
  });
});
