"use client";

import { memo, useState } from "react";
import type { PlanWeek, PlanWorkout, PreferredUnits } from "@/lib/types";
import { formatDistance } from "@/lib/units";
import { WORKOUT_TYPE_LABELS, formatWorkoutType } from "@/lib/workouts";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Legend items — key + dot color. Labels pulled from WORKOUT_TYPE_LABELS at
// render time so they can't drift from the canonical map. Types sharing a
// dot color (e.g. tempo/fartlek both amber) are filtered by the legend so
// only colors that need explaining appear.
const LEGEND_ITEMS: { key: string; dot: string }[] = [
  { key: "easy", dot: "bg-emerald-400" },
  { key: "recovery", dot: "bg-emerald-400" },
  { key: "long_run", dot: "bg-blue-400" },
  { key: "tempo", dot: "bg-amber-400" },
  { key: "interval", dot: "bg-red-400" },
  { key: "hill", dot: "bg-orange-400" },
  { key: "rest", dot: "bg-gray-300" },
];

const WORKOUT_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  easy: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", dot: "bg-emerald-400" },
  recovery: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", dot: "bg-emerald-400" },
  long_run: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", dot: "bg-blue-400" },
  tempo: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", dot: "bg-amber-400" },
  interval: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", dot: "bg-red-400" },
  hill: { bg: "bg-orange-50", border: "border-orange-200", text: "text-orange-700", dot: "bg-orange-400" },
  repetition: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", dot: "bg-red-400" },
  fartlek: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", dot: "bg-amber-400" },
  rest: { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-400", dot: "bg-gray-300" },
};

const DEFAULT_COLOR = { bg: "bg-gray-50", border: "border-gray-200", text: "text-gray-600", dot: "bg-gray-300" };

const PHASE_COLORS: Record<string, string> = {
  base: "bg-emerald-100 text-emerald-800",
  build: "bg-amber-100 text-amber-800",
  peak: "bg-red-100 text-red-800",
  taper: "bg-blue-100 text-blue-800",
  recovery: "bg-gray-100 text-gray-600",
};

const WorkoutCell = memo(function WorkoutCell({ workout, onClick, units }: { workout: PlanWorkout | null; onClick?: () => void; units: PreferredUnits }) {
  if (!workout) {
    return (
      <div className="h-full min-h-[68px] border border-gray-100 rounded-lg bg-gray-50/30" />
    );
  }

  if (workout.workout_type === "rest") {
    return (
      <div className="h-full min-h-[68px] border border-gray-100 rounded-lg bg-gray-50/50 flex items-center justify-center">
        <span className="text-xs text-gray-300">Rest</span>
      </div>
    );
  }

  const colors = WORKOUT_COLORS[workout.workout_type] ?? DEFAULT_COLOR;

  const ariaLabel = `${formatWorkoutType(workout.workout_type)}${workout.distance_km != null ? ` - ${formatDistance(workout.distance_km, units)}` : ""}`;

  return (
    <button
      onClick={onClick}
      aria-label={ariaLabel}
      className={`h-full min-h-[68px] w-full rounded-lg border p-2 text-left transition-all hover:shadow-md hover:scale-[1.02] ${colors.bg} ${colors.border}`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${colors.dot}`} />
        <span className={`text-xs font-semibold ${colors.text} truncate`}>
          {formatWorkoutType(workout.workout_type)}
        </span>
      </div>
      {workout.distance_km != null && (
        <div className="text-[11px] text-gray-500">
          {formatDistance(workout.distance_km, units)}
        </div>
      )}
      {workout.pace_zone && (
        <div className="text-[10px] text-gray-400 truncate">
          {workout.pace_zone}
        </div>
      )}
    </button>
  );
});

function WorkoutDetail({ workout, onClose, units }: { workout: PlanWorkout; onClose: () => void; units: PreferredUnits }) {
  const colors = WORKOUT_COLORS[workout.workout_type] ?? DEFAULT_COLOR;

  return (
    <div className={`rounded-xl border p-5 ${colors.bg} ${colors.border}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className={`font-semibold ${colors.text}`}>
            {formatWorkoutType(workout.workout_type)}
          </h4>
          {workout.pace_zone && (
            <span className="text-sm text-gray-500">{workout.pace_zone}</span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-sm"
          aria-label="Close details"
        >
          ✕
        </button>
      </div>

      {workout.description && (
        <p className="text-sm text-gray-700 mb-3">{workout.description}</p>
      )}

      <div className="flex flex-wrap gap-4 text-sm text-gray-600">
        {workout.distance_km != null && (
          <div>
            <span className="text-xs text-gray-400 block">Distance</span>
            <span className="font-medium">{formatDistance(workout.distance_km, units)}</span>
          </div>
        )}
        {workout.duration_minutes != null && (
          <div>
            <span className="text-xs text-gray-400 block">Duration</span>
            <span className="font-medium">{workout.duration_minutes} min</span>
          </div>
        )}
        {workout.tss != null && workout.tss > 0 && (
          <div>
            <span className="text-xs text-gray-400 block">TSS</span>
            <span className="font-medium">{workout.tss}</span>
          </div>
        )}
        {workout.intensity != null && (
          <div>
            <span className="text-xs text-gray-400 block">Intensity</span>
            <span className="font-medium">{Math.round(workout.intensity * 100)}%</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Legend() {
  // Deduplicate by dot color so users don't see 3 amber rows.
  const seen = new Set<string>();
  const items = LEGEND_ITEMS.filter((t) => {
    if (seen.has(t.dot)) return false;
    seen.add(t.dot);
    return true;
  });

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {items.map((t) => (
        <div key={t.key} className="flex items-center gap-1.5">
          <span className={`w-2.5 h-2.5 rounded-full ${t.dot}`} />
          <span className="text-xs text-gray-500">
            {WORKOUT_TYPE_LABELS[t.key] ?? t.key}
          </span>
        </div>
      ))}
    </div>
  );
}

interface PlanCalendarProps {
  weeks: PlanWeek[];
  units?: PreferredUnits;
  currentWeekNumber?: number;
}

export function PlanCalendar({ weeks, units = "metric", currentWeekNumber }: PlanCalendarProps) {
  // Mon=0..Sun=6
  const todayDayIndex = (new Date().getDay() + 6) % 7;
  const [selectedWorkout, setSelectedWorkout] = useState<{
    week: number;
    workout: PlanWorkout;
  } | null>(null);

  return (
    <div className="space-y-1">
      {/* Legend */}
      <div className="mb-4">
        <Legend />
      </div>

      <div className="overflow-x-auto -mx-2 px-2 pb-2">
      <div className="min-w-[640px]">
      {/* Day headers */}
      <div className="grid grid-cols-[60px_repeat(7,1fr)] sm:grid-cols-[80px_repeat(7,1fr)] gap-1.5">
        <div />
        {DAY_LABELS.map((day, i) => (
          <div
            key={`${day}-${i}`}
            className={`text-center text-xs font-semibold py-2 border-b ${
              currentWeekNumber && i === todayDayIndex
                ? "text-blue-600 border-blue-300"
                : "text-gray-500 border-gray-200"
            }`}
          >
            {day}
            {currentWeekNumber && i === todayDayIndex && (
              <span className="block text-[9px] font-semibold text-blue-500">Today</span>
            )}
          </div>
        ))}
      </div>

      {/* Week rows */}
      {weeks.map((week) => {
        const phaseClass = PHASE_COLORS[week.phase] ?? "bg-gray-100 text-gray-600";
        const isCurrentWeek = currentWeekNumber === week.week_number;
        const workoutsByDay: (PlanWorkout | null)[] = Array.from({ length: 7 }, (_, i) => {
          return week.workouts.find((w) => w.day != null && w.day === i + 1) ?? null;
        });

        return (
          <div key={week.week_number} className={`group ${isCurrentWeek ? "bg-blue-50/50 rounded-lg -mx-2 px-2" : ""}`}>
            <div className="grid grid-cols-[60px_repeat(7,1fr)] sm:grid-cols-[80px_repeat(7,1fr)] gap-1.5 py-1.5">
              {/* Week label */}
              <div className="flex flex-col justify-center items-start gap-1.5 pr-2 border-r border-gray-200">
                <span className={`text-xs font-bold ${isCurrentWeek ? "text-blue-700" : "text-gray-700"}`}>
                  Wk {week.week_number}
                  {isCurrentWeek && <span className="block text-[9px] text-blue-500 font-semibold">Current</span>}
                </span>
                <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${phaseClass}`}>
                  {week.phase}
                </span>
              </div>

              {/* Day cells */}
              {workoutsByDay.map((workout, dayIdx) => (
                <WorkoutCell
                  key={dayIdx}
                  workout={workout}
                  units={units}
                  onClick={
                    workout && workout.workout_type !== "rest"
                      ? () =>
                          setSelectedWorkout({
                            week: week.week_number,
                            workout,
                          })
                      : undefined
                  }
                />
              ))}
            </div>

            {/* Expanded workout detail */}
            {selectedWorkout?.week === week.week_number && (
              <div className="mt-1.5 ml-[68px] sm:ml-[88px]">
                <WorkoutDetail
                  workout={selectedWorkout.workout}
                  units={units}
                  onClose={() => setSelectedWorkout(null)}
                />
              </div>
            )}

            {/* Week notes */}
            {week.notes && (
              <div className="ml-[68px] sm:ml-[88px] mt-1 mb-1 text-[11px] text-gray-400 italic line-clamp-1">
                {week.notes}
              </div>
            )}

            {/* Row divider */}
            <div className="border-b border-gray-100" />
          </div>
        );
      })}
      </div>
      </div>
    </div>
  );
}
