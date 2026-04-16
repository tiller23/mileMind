/**
 * Shared workout-type display labels + formatter.
 *
 * The planner emits workout_type values like "easy", "long_run", etc.
 * This map is the canonical display label for each type. Surfaces that
 * render workout rows (PlanCalendar, dashboard ThisWeek card) import
 * formatWorkoutType from here to keep labels consistent.
 */

export const WORKOUT_TYPE_LABELS: Record<string, string> = {
  easy: "Easy Run",
  recovery: "Recovery",
  long_run: "Long Run",
  tempo: "Tempo",
  interval: "Intervals",
  hill: "Hills",
  repetition: "Speed Work",
  fartlek: "Mixed Pace",
  marathon_pace: "Marathon Pace",
  cross_train: "Cross Training",
  rest: "Rest",
};

export function formatWorkoutType(type: string): string {
  return (
    WORKOUT_TYPE_LABELS[type] ??
    type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}
