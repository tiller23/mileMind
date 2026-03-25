"use client";

import Link from "next/link";
import { useDemoPlans } from "@/lib/hooks";
import { Logo } from "@/components/Logo";

const PERSONA_INFO: Record<string, { title: string; subtitle: string; description: string; color: string }> = {
  "5K": {
    title: "Beginner 5K",
    subtitle: "Sarah Chen \u2022 8 weeks",
    description: "Building from 12 km/week to a confident 5K finish. Conservative progression with room for walk breaks.",
    color: "from-emerald-500 to-emerald-700",
  },
  "Half Marathon": {
    title: "Intermediate Half Marathon",
    subtitle: "Marcus Rodriguez \u2022 12 weeks",
    description: "Targeting sub-1:35 with tempo runs, speed work, and a structured taper. Injury history factored in.",
    color: "from-blue-500 to-blue-700",
  },
  "Marathon": {
    title: "Advanced Marathon",
    subtitle: "Elena Vasquez \u2022 16 weeks",
    description: "Chasing sub-3:05 on 95 km/week. Race-pace tempos, 32K long runs, and full periodization.",
    color: "from-purple-500 to-purple-700",
  },
};

export default function DemoPage() {
  const { data: plans, isLoading } = useDemoPlans();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/">
            <Logo size="sm" />
          </Link>
          <Link
            href="/login"
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
          >
            Sign in &rarr;
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-12">
        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">
            Sample Training Plans
          </h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Browse plans built by MileMind for three different runners.
            Every workout, every week, every coaching decision &mdash; all generated and reviewed by AI.
          </p>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-2/3 mb-4" />
                <div className="h-3 bg-gray-100 rounded w-1/2 mb-6" />
                <div className="space-y-2">
                  <div className="h-3 bg-gray-100 rounded" />
                  <div className="h-3 bg-gray-100 rounded w-4/5" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {plans?.map((plan) => {
              const event = plan.goal_event || "Plan";
              const info = PERSONA_INFO[event];
              if (!info) return null;

              return (
                <Link
                  key={plan.id}
                  href={`/demo/${plan.id}`}
                  className="group bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
                >
                  <div className={`h-2 bg-gradient-to-r ${info.color}`} />
                  <div className="p-6">
                    <h2 className="text-lg font-semibold text-gray-900 group-hover:text-indigo-600 transition-colors mb-1">
                      {info.title}
                    </h2>
                    <p className="text-sm text-gray-500 mb-4">{info.subtitle}</p>
                    <p className="text-sm text-gray-600 leading-relaxed">
                      {info.description}
                    </p>
                    <div className="mt-4 flex items-center gap-4 text-xs text-gray-400">
                      <span>{plan.week_count} weeks</span>
                      <span>&bull;</span>
                      <span className="text-emerald-600 font-medium">Approved</span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}

        {/* How it works */}
        <div className="mt-16 text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">How plans are built</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-left">
            <div>
              <div className="text-2xl mb-2">1.</div>
              <h3 className="font-medium text-gray-900 mb-1">Design</h3>
              <p className="text-sm text-gray-600">
                An AI planner builds a periodized training block using
                your profile, goals, and proven exercise science models.
              </p>
            </div>
            <div>
              <div className="text-2xl mb-2">2.</div>
              <h3 className="font-medium text-gray-900 mb-1">Review</h3>
              <p className="text-sm text-gray-600">
                A separate AI reviewer scores the plan on safety, progression,
                specificity, and feasibility. If it doesn&apos;t pass, it goes back for revision.
              </p>
            </div>
            <div>
              <div className="text-2xl mb-2">3.</div>
              <h3 className="font-medium text-gray-900 mb-1">Refine</h3>
              <p className="text-sm text-gray-600">
                The planner revises based on feedback until the plan is approved.
                You can see the full decision log on each plan.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
