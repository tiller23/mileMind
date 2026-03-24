"use client";

import Link from "next/link";
import { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { PlanGenerationLoader } from "@/components/PlanGenerationLoader";
import { ShoeIcon, RunnerIcon } from "@/components/Icons";
import { useAuthGuard, useGeneratePlan, usePlans, usePlan, useProfile } from "@/lib/hooks";
import type { PlanWeek, PlanWorkout, PreferredUnits } from "@/lib/types";
import { formatDistance } from "@/lib/units";

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

function ThisWeekCard({ week, weekNumber, totalWeeks, phase, planId, units }: {
  week: PlanWeek;
  weekNumber: number;
  totalWeeks: number;
  phase: string;
  planId: string;
  units: PreferredUnits;
}) {
  const workoutsByDay: (PlanWorkout | null)[] = Array.from({ length: 7 }, (_, i) => {
    return week.workouts.find((w) => w.day != null && w.day === i + 1) ?? null;
  });

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-semibold text-gray-900">This Week</h2>
          <p className="text-sm text-gray-500">
            Week {weekNumber} of {totalWeeks}
            <span className="mx-1.5 text-gray-300">&middot;</span>
            <span className="capitalize">{phase}</span> phase
          </p>
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

          return (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className="text-[10px] font-medium text-gray-400">{day}</span>
              <div className={`w-full rounded-lg border p-2 min-h-[56px] flex flex-col items-center justify-center gap-1 ${
                isRest ? "border-gray-100 bg-gray-50/50" : "border-gray-200 bg-white"
              }`}>
                <span className={`w-2 h-2 rounded-full ${dot}`} />
                <span className={`text-[10px] font-medium text-center leading-tight ${
                  isRest ? "text-gray-300" : "text-gray-600"
                }`}>
                  {workout ? formatWorkoutType(workout.workout_type) : ""}
                </span>
                {workout?.distance_km != null && !isRest && (
                  <span className="text-[10px] text-gray-400">
                    {formatDistance(workout.distance_km, units)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

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

function estimateCurrentWeek(createdAt: string, totalWeeks: number): number {
  const created = new Date(createdAt);
  const now = new Date();
  const diffMs = now.getTime() - created.getTime();
  const diffWeeks = Math.floor(diffMs / (7 * 24 * 60 * 60 * 1000)) + 1;
  return Math.min(Math.max(diffWeeks, 1), totalWeeks);
}

export default function DashboardPage() {
  const { isAuthenticated } = useAuthGuard();
  const { data: profileData, isLoading: profileLoading } = useProfile();
  const { data: plansData, isLoading: plansLoading } = usePlans();
  const generatePlan = useGeneratePlan();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const needsOnboarding = !profileLoading && profileData === null;

  // Find the active plan for "This Week" card
  const activePlanSummary = plansData?.find((p) => p.status === "active");
  const { data: activePlanDetail } = usePlan(activePlanSummary?.id ?? "");

  if (!isAuthenticated) return null;

  async function handleGenerate() {
    const result = await generatePlan.mutateAsync({ change_type: "full" });
    setActiveJobId(result.job_id);
  }

  // Compute current week from active plan
  const activeWeeks = activePlanDetail?.plan_data?.weeks;
  const currentWeekNum = activePlanDetail
    ? estimateCurrentWeek(activePlanDetail.created_at, activeWeeks?.length ?? 0)
    : null;
  const currentWeek = activeWeeks && currentWeekNum
    ? activeWeeks.find((w) => w.week_number === currentWeekNum) ?? activeWeeks[0]
    : null;

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            {profileData && (
              <p className="text-sm text-gray-500 mt-0.5">
                Welcome back, {profileData.name}
              </p>
            )}
          </div>
          {profileData && !activeJobId && (
            <button
              onClick={handleGenerate}
              disabled={generatePlan.isPending}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
            >
              {generatePlan.isPending ? "Starting..." : "New Plan"}
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

        {activeJobId && (
          <div className="bg-white border border-gray-200 rounded-xl p-6 mb-6 shadow-sm">
            <PlanGenerationLoader jobId={activeJobId} />
          </div>
        )}

        {/* This Week card */}
        {currentWeek && activePlanSummary && activeWeeks && currentWeekNum && (
          <ThisWeekCard
            week={currentWeek}
            weekNumber={currentWeekNum}
            totalWeeks={activeWeeks.length}
            phase={currentWeek.phase}
            planId={activePlanSummary.id}
            units={profileData?.preferred_units ?? "metric"}
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
                !activeJobId && (
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
                      onClick={handleGenerate}
                      disabled={generatePlan.isPending}
                      className="px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
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
