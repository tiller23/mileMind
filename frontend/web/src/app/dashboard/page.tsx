"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { PlanGenerationLoader } from "@/components/PlanGenerationLoader";
import { ShoeIcon, RunnerIcon } from "@/components/Icons";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthGuard, useActiveJob, useGeneratePlan, usePlans, usePlan, useProfile, useUpdatePlanStartDate, useStravaStatus, useStravaActivities } from "@/lib/hooks";
import type { PlanWeek, PlanWorkout, PreferredUnits, ProfileResponse, WorkoutLogResponse } from "@/lib/types";
import { formatDistance } from "@/lib/units";

const GOAL_LABELS: Record<string, string> = {
  general_fitness: "General Fitness",
  "5K": "5K",
  "10K": "10K",
  half_marathon: "Half Marathon",
  marathon: "Marathon",
  ultra: "Ultra",
};

const RISK_LABELS: Record<string, string> = {
  conservative: "Conservative",
  moderate: "Moderate",
  aggressive: "Aggressive",
};

const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

const WORKOUT_DOT_COLORS: Record<string, string> = {
  easy: "bg-emerald-400",
  recovery: "bg-emerald-400",
  long_run: "bg-blue-400",
  tempo: "bg-amber-400",
  interval: "bg-red-400",
  hill: "bg-orange-400",
  rest: "bg-gray-200",
};

function formatWorkoutType(type: string): string {
  const names: Record<string, string> = {
    easy: "Easy Run", recovery: "Recovery", long_run: "Long Run",
    tempo: "Tempo", interval: "Intervals", hill: "Hills", rest: "Rest",
  };
  return names[type] ?? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Compute the calendar date for a given week/day in the plan. */
function getPlanDayDate(planStartDate: string, weekNumber: number, dayIndex: number): string {
  const start = new Date(planStartDate + "T00:00:00");
  const offset = (weekNumber - 1) * 7 + dayIndex;
  const date = new Date(start);
  date.setDate(start.getDate() + offset);
  return date.toISOString().split("T")[0];
}

/** Find an actual workout log matching a specific calendar date. */
function findActualForDate(actuals: WorkoutLogResponse[], dateStr: string): WorkoutLogResponse | undefined {
  return actuals.find((a) => a.completed_at.split("T")[0] === dateStr);
}

function ThisWeekCard({ week, weekNumber, totalWeeks, phase, planId, units, planStartDate, createdAt, actuals, isCurrentWeek = true, onPrevWeek, onNextWeek, onResetWeek }: {
  week: PlanWeek;
  weekNumber: number;
  totalWeeks: number;
  phase: string;
  planId: string;
  units: PreferredUnits;
  planStartDate: string | null | undefined;
  createdAt: string;
  actuals?: WorkoutLogResponse[];
  isCurrentWeek?: boolean;
  onPrevWeek?: () => void;
  onNextWeek?: () => void;
  onResetWeek?: () => void;
}) {
  const updateStartDate = useUpdatePlanStartDate();
  const [editingDate, setEditingDate] = useState(false);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  // Default to plan_start_date, or derive from created_at for older plans
  const effectiveStart = planStartDate ?? createdAt.split("T")[0];
  const [newDate, setNewDate] = useState(effectiveStart);

  const workoutsByDay: (PlanWorkout | null)[] = Array.from({ length: 7 }, (_, i) => {
    return week.workouts.find((w) => w.day != null && w.day === i + 1) ?? null;
  });

  function handleSaveDate() {
    if (!newDate) return;
    updateStartDate.mutate(
      { planId, data: { plan_start_date: newDate } },
      { onSuccess: () => setEditingDate(false) },
    );
  }

  const formattedStart = new Date(effectiveStart + "T00:00:00").toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-semibold text-gray-900">
              {isCurrentWeek ? "This Week" : `Week ${weekNumber}`}
            </h2>
            <div className="flex items-center gap-0.5">
              <button
                onClick={onPrevWeek}
                disabled={!onPrevWeek}
                className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-default transition-colors"
                aria-label="Previous week"
              >
                <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button
                onClick={onNextWeek}
                disabled={!onNextWeek}
                className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-default transition-colors"
                aria-label="Next week"
              >
                <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
              {onResetWeek && (
                <button
                  onClick={onResetWeek}
                  className="ml-1 px-2 py-0.5 text-[10px] font-medium text-blue-600 bg-blue-50 rounded-full hover:bg-blue-100 transition-colors"
                >
                  Today
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <p className="text-sm text-gray-500">
              Week {weekNumber} of {totalWeeks}
              <span className="mx-1.5 text-gray-300">&middot;</span>
              <span className="capitalize">{phase}</span> phase
              <span className="mx-1.5 text-gray-300">&middot;</span>
              Started {formattedStart}
            </p>
            {!editingDate && (
              <button
                onClick={() => { setNewDate(effectiveStart); setEditingDate(true); }}
                className="text-xs text-blue-500 hover:text-blue-700 font-medium transition-colors"
              >
                Adjust
              </button>
            )}
          </div>
          {editingDate && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-2">
                Shift your plan timeline. Your workouts stay the same &mdash;
                only which week you&apos;re on changes.
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  aria-label="Adjust plan start date"
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                  onClick={handleSaveDate}
                  disabled={updateStartDate.isPending || !newDate}
                  className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {updateStartDate.isPending ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={() => setEditingDate(false)}
                  className="px-3 py-1.5 text-gray-500 hover:text-gray-700 text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
        <Link
          href={`/plan/${planId}`}
          className="text-sm text-blue-600 hover:underline"
        >
          Full plan &rarr;
        </Link>
      </div>

      <div className="grid grid-cols-7 gap-2">
        {DAY_LABELS.map((day, i) => {
          const workout = workoutsByDay[i];
          const dot = workout
            ? WORKOUT_DOT_COLORS[workout.workout_type] ?? "bg-gray-300"
            : "bg-transparent";
          const isRest = !workout || workout.workout_type === "rest";
          // JS getDay(): Sun=0..Sat=6 → Mon-indexed: Mon=0..Sun=6
          const todayIndex = (new Date().getDay() + 6) % 7;
          const isToday = i === todayIndex;

          const isSelected = selectedDay === i;
          // Find actual Strava data for this day
          const dayDate = actuals && effectiveStart
            ? getPlanDayDate(effectiveStart, weekNumber, i)
            : null;
          const actual = dayDate ? findActualForDate(actuals ?? [], dayDate) : undefined;
          const hasActual = !!actual;
          const canTap = (workout && !isRest) || hasActual;

          return (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className={`text-[10px] font-medium ${
                isToday ? "text-blue-600" : "text-gray-400"
              }`}>{day}</span>
              <button
                type="button"
                disabled={!canTap}
                onClick={() => canTap && setSelectedDay(isSelected ? null : i)}
                className={`w-full rounded-lg border p-2 min-h-[56px] flex flex-col items-center justify-center gap-1 transition-all ${
                  isSelected
                    ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                    : isToday
                      ? "border-blue-400 bg-blue-50 ring-1 ring-blue-200"
                      : isRest && !hasActual
                        ? "border-gray-100 bg-gray-50/50"
                        : hasActual && isRest
                          ? "border-green-200 bg-green-50/50 hover:border-green-300 hover:shadow-sm"
                          : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
                } ${canTap ? "cursor-pointer" : "cursor-default"}`}>
                {hasActual && isRest ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-green-400" />
                    <span className="text-[10px] font-medium text-green-700 text-center leading-tight">
                      {actual.notes || "Run"}
                    </span>
                    <span className="text-[9px] font-medium text-green-600">
                      {formatDistance(actual.actual_distance_km, units)}
                    </span>
                  </>
                ) : (
                  <>
                    <span className={`w-2 h-2 rounded-full ${dot}`} />
                    <span className={`text-[10px] font-medium text-center leading-tight ${
                      isToday ? "text-blue-700" : isRest ? "text-gray-300" : "text-gray-600"
                    }`}>
                      {workout ? formatWorkoutType(workout.workout_type) : ""}
                    </span>
                    {workout?.distance_km != null && !isRest && (
                      <span className={`text-[10px] ${isToday ? "text-blue-500" : "text-gray-400"}`}>
                        {formatDistance(workout.distance_km, units)}
                      </span>
                    )}
                    {hasActual && (
                      <span className="text-[9px] font-medium text-green-600">
                        {formatDistance(actual.actual_distance_km, units)}
                      </span>
                    )}
                  </>
                )}
              </button>
              {isToday && (
                <span className="text-[9px] font-semibold text-blue-500">Today</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Expanded workout detail */}
      {selectedDay !== null && (() => {
        const w = workoutsByDay[selectedDay];
        const dayDate = actuals && effectiveStart
          ? getPlanDayDate(effectiveStart, weekNumber, selectedDay)
          : null;
        const actual = dayDate ? findActualForDate(actuals ?? [], dayDate) : undefined;
        if (!w && !actual) return null;

        return (
          <div className="mt-3 space-y-2">
            {/* Planned workout */}
            {w && w.workout_type !== "rest" && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">Planned</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-sm font-semibold text-gray-900">
                        {formatWorkoutType(w.workout_type)}
                      </span>
                      {w.pace_zone && (
                        <span className="text-xs text-gray-500">{w.pace_zone}</span>
                      )}
                    </div>
                  </div>
                  {!actual && (
                    <button
                      onClick={() => setSelectedDay(null)}
                      className="text-gray-400 hover:text-gray-600 text-sm"
                    >
                      &#10005;
                    </button>
                  )}
                </div>
                {w.description && (
                  <p className="text-sm text-gray-700 leading-relaxed">{w.description}</p>
                )}
                <div className="flex gap-4 mt-2 text-xs text-gray-500">
                  {w.distance_km != null && (
                    <span>{formatDistance(w.distance_km, units)}</span>
                  )}
                  {w.duration_minutes != null && (
                    <span>{w.duration_minutes} min</span>
                  )}
                </div>
              </div>
            )}

            {/* Actual Strava data */}
            {actual && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <span className="text-[10px] font-medium text-green-600 uppercase tracking-wide">Actual (Strava)</span>
                    <div className="mt-0.5">
                      <span className="text-sm font-semibold text-green-800">
                        {actual.notes || "Run"}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedDay(null)}
                    className="text-gray-400 hover:text-gray-600 text-sm"
                  >
                    &#10005;
                  </button>
                </div>
                <div className="flex flex-wrap gap-4 mt-1 text-xs text-green-700">
                  <div>
                    <span className="text-green-500 block">Distance</span>
                    <span className="font-medium">{formatDistance(actual.actual_distance_km, units)}</span>
                  </div>
                  <div>
                    <span className="text-green-500 block">Duration</span>
                    <span className="font-medium">{actual.actual_duration_minutes.toFixed(0)} min</span>
                  </div>
                  {actual.avg_heart_rate && (
                    <div>
                      <span className="text-green-500 block">Avg HR</span>
                      <span className="font-medium">{actual.avg_heart_rate} bpm</span>
                    </div>
                  )}
                  {actual.actual_distance_km > 0 && (
                    <div>
                      <span className="text-green-500 block">Pace</span>
                      <span className="font-medium">
                        {(() => {
                          const dist = units === "imperial"
                            ? actual.actual_distance_km * 0.621371
                            : actual.actual_distance_km;
                          const paceMin = actual.actual_duration_minutes / dist;
                          const mins = Math.floor(paceMin);
                          const secs = Math.round((paceMin - mins) * 60);
                          return `${mins}:${secs.toString().padStart(2, "0")} /${units === "imperial" ? "mi" : "km"}`;
                        })()}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {week.notes && (
        <p className="mt-3 text-xs text-gray-400 italic">{week.notes}</p>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="h-5 w-32 bg-gray-200 rounded" />
          <div className="h-5 w-16 bg-gray-200 rounded" />
        </div>
        <div className="h-4 w-24 bg-gray-100 rounded" />
      </div>
      <div className="flex gap-2">
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
      </div>
    </div>
  );
}

function ConfirmGeneratePanel({ profile, startDate, onStartDateChange, onConfirm, onCancel, isPending }: {
  profile: ProfileResponse;
  startDate: string;
  onStartDateChange: (date: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const mileageDisplay = profile.preferred_units === "imperial"
    ? `${(profile.weekly_mileage_base * 0.621371).toFixed(0)} mi/week`
    : `${profile.weekly_mileage_base} km/week`;

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden mb-6">
      <div className="p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">
          Generate Your Plan
        </h2>
        <p className="text-sm text-gray-500 mb-5">
          Review your details before we build your plan. This takes 1-3 minutes once started.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 mb-5">
          <div>
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Goal</span>
            <p className="text-sm text-gray-900 mt-0.5">
              {GOAL_LABELS[profile.goal_distance] ?? profile.goal_distance}
              {profile.goal_time_minutes ? ` in ${profile.goal_time_minutes} min` : ""}
            </p>
          </div>
          <div>
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Current Mileage</span>
            <p className="text-sm text-gray-900 mt-0.5">{mileageDisplay}</p>
          </div>
          <div>
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Plan Duration</span>
            <p className="text-sm text-gray-900 mt-0.5">{profile.plan_duration_weeks} weeks</p>
          </div>
          <div>
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Training Days</span>
            <p className="text-sm text-gray-900 mt-0.5">{profile.training_days_per_week} days/week</p>
          </div>
          <div>
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Approach</span>
            <p className="text-sm text-gray-900 mt-0.5">{RISK_LABELS[profile.risk_tolerance] ?? profile.risk_tolerance}</p>
          </div>
          <div>
            <label htmlFor="plan-start-date" className="text-xs font-medium text-gray-400 uppercase tracking-wide">Start Date</label>
            <input
              id="plan-start-date"
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="mt-0.5 px-2 py-1 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-full"
            />
          </div>
        </div>

        <Link
          href="/onboarding"
          className="text-xs text-blue-600 hover:underline"
        >
          Need to update your profile first?
        </Link>
      </div>

      <div className="bg-gray-50 border-t border-gray-200 px-6 py-4 flex items-center justify-end gap-3">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={isPending}
          className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          {isPending ? "Starting..." : "Generate Plan"}
        </button>
      </div>
    </div>
  );
}

function estimateCurrentWeek(planStartDate: string | null | undefined, createdAt: string, totalWeeks: number): number {
  const start = planStartDate ? new Date(planStartDate) : new Date(createdAt);
  const now = new Date();
  const diffMs = now.getTime() - start.getTime();
  const diffWeeks = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(diffWeeks, 1), totalWeeks);
}

function getNextMonday(): string {
  const today = new Date();
  const dayOfWeek = today.getDay();
  const daysUntilMonday = dayOfWeek === 0 ? 1 : (8 - dayOfWeek) % 7 || 7;
  const nextMonday = new Date(today);
  nextMonday.setDate(today.getDate() + daysUntilMonday);
  return nextMonday.toISOString().split("T")[0];
}

export default function DashboardPage() {
  const { isAuthenticated } = useAuthGuard();
  const { data: profileData, isLoading: profileLoading } = useProfile();
  const { data: plansData, isLoading: plansLoading } = usePlans();
  const generatePlan = useGeneratePlan();
  const queryClient = useQueryClient();
  const { data: existingActiveJob } = useActiveJob();
  const { data: stravaStatus } = useStravaStatus();
  const { data: stravaActivities } = useStravaActivities(
    stravaStatus?.connected ? 100 : 0,
  );
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(getNextMonday);
  const [showConfirm, setShowConfirm] = useState(false);
  const [weekOffset, setWeekOffset] = useState(0);

  // Resume showing the loader if there's a running job (e.g., navigated away and back)
  useEffect(() => {
    if (existingActiveJob && !activeJobId) {
      setActiveJobId(existingActiveJob.job_id);
    }
  }, [existingActiveJob, activeJobId]);

  const needsOnboarding = !profileLoading && profileData === null;

  // Find the active plan for "This Week" card
  const activePlanSummary = plansData?.find((p) => p.status === "active");
  const { data: activePlanDetail } = usePlan(activePlanSummary?.id);

  if (!isAuthenticated) return null;

  async function handleGenerate() {
    const result = await generatePlan.mutateAsync({
      change_type: "full",
      plan_start_date: startDate,
    });
    setShowConfirm(false);
    setActiveJobId(result.job_id);
  }

  // Compute current week from active plan
  const activeWeeks = activePlanDetail?.plan_data?.weeks;
  const autoWeekNum = activePlanDetail
    ? estimateCurrentWeek(
        activePlanDetail.plan_data?.plan_start_date,
        activePlanDetail.created_at,
        activeWeeks?.length ?? 0,
      )
    : null;
  const viewWeekNum = autoWeekNum
    ? Math.min(Math.max(autoWeekNum + weekOffset, 1), activeWeeks?.length ?? 1)
    : null;
  const isCurrentWeek = viewWeekNum === autoWeekNum;
  const currentWeek = activeWeeks && viewWeekNum
    ? activeWeeks.find((w) => w.week_number === viewWeekNum) ?? activeWeeks[0]
    : null;

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            {profileData && (
              <p className="text-sm text-gray-500 mt-0.5">
                Welcome back, {profileData.name}
              </p>
            )}
          </div>
          {profileData && !activeJobId && !showConfirm && (
            <button
              onClick={() => setShowConfirm(true)}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-sm"
            >
              New Plan
            </button>
          )}
        </div>

        {needsOnboarding && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-8 text-center shadow-sm mb-6">
            <div className="mx-auto w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center mb-4">
              <ShoeIcon className="w-6 h-6 text-amber-600" />
            </div>
            <h2 className="text-lg font-semibold text-amber-800 mb-2">
              Complete Your Profile
            </h2>
            <p className="text-amber-700 mb-5 text-sm">
              We need a few details before building your plan.
            </p>
            <Link
              href="/onboarding"
              className="inline-block px-5 py-2.5 bg-amber-600 text-white rounded-xl font-medium hover:bg-amber-700 transition-colors"
            >
              Get Started
            </Link>
          </div>
        )}

        {generatePlan.isError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 shadow-sm">
            <p className="text-red-800 text-sm">
              {generatePlan.error instanceof Error
                ? generatePlan.error.message
                : "Failed to start plan generation"}
            </p>
          </div>
        )}

        {showConfirm && profileData && !activeJobId && (
          <ConfirmGeneratePanel
            profile={profileData}
            startDate={startDate}
            onStartDateChange={setStartDate}
            onConfirm={handleGenerate}
            onCancel={() => setShowConfirm(false)}
            isPending={generatePlan.isPending}
          />
        )}

        {activeJobId && (
          <div className="bg-white border border-gray-200 rounded-xl p-6 mb-6 shadow-sm">
            <PlanGenerationLoader
              jobId={activeJobId}
              onComplete={() => {
                setActiveJobId(null);
                queryClient.invalidateQueries({ queryKey: ["plans"] });
                queryClient.invalidateQueries({ queryKey: ["active-job"] });
              }}
            />
          </div>
        )}

        {/* This Week card */}
        {currentWeek && activePlanSummary && activeWeeks && viewWeekNum && (
          <ThisWeekCard
            week={currentWeek}
            weekNumber={viewWeekNum}
            totalWeeks={activeWeeks.length}
            phase={currentWeek.phase}
            planId={activePlanSummary.id}
            units={profileData?.preferred_units ?? "metric"}
            planStartDate={activePlanDetail?.plan_data?.plan_start_date}
            createdAt={activePlanDetail?.created_at ?? activePlanSummary.created_at}
            actuals={stravaActivities ?? undefined}
            isCurrentWeek={isCurrentWeek}
            onPrevWeek={viewWeekNum > 1 ? () => setWeekOffset((o) => o - 1) : undefined}
            onNextWeek={viewWeekNum < activeWeeks.length ? () => setWeekOffset((o) => o + 1) : undefined}
            onResetWeek={!isCurrentWeek ? () => setWeekOffset(0) : undefined}
          />
        )}

        {profileLoading || plansLoading ? (
          <div className="space-y-4">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <>
            {plansData && plansData.length > 0 && (
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                Your Plans
              </h2>
            )}
            <div className="space-y-3">
              {plansData && plansData.length > 0 ? (
                plansData.map((plan) => (
                  <Link
                    key={plan.id}
                    href={`/plan/${plan.id}`}
                    className="block bg-white border border-gray-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <h3 className="font-medium text-gray-900">
                          {plan.goal_event
                            ? `${plan.goal_event} Plan`
                            : "Training Plan"}
                        </h3>
                        {plan.week_count && (
                          <span className="text-xs text-gray-400">
                            {plan.week_count} weeks
                          </span>
                        )}
                        {plan.status === "archived" && (
                          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                            Archived
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-gray-400">
                        {new Date(plan.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </Link>
                ))
              ) : (
                !needsOnboarding &&
                profileData &&
                !activeJobId &&
                !showConfirm && (
                  <div className="text-center py-16">
                    <div className="mx-auto w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mb-4">
                      <RunnerIcon className="w-7 h-7 text-blue-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-800 mb-1">
                      Ready to start training
                    </h3>
                    <p className="text-sm text-gray-500 mb-6">
                      Create your first training plan to get started.
                    </p>
                    <button
                      onClick={() => setShowConfirm(true)}
                      className="px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-sm"
                    >
                      Create My Plan
                    </button>
                  </div>
                )
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
