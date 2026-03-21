"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { useAuthGuard, useProfile, useUpsertProfile } from "@/lib/hooks";
import type { ProfileUpdate, RiskTolerance } from "@/lib/types";

const GOAL_OPTIONS: { value: string; label: string }[] = [
  { value: "general_fitness", label: "General fitness (no specific race)" },
  { value: "5K", label: "5K" },
  { value: "10K", label: "10K" },
  { value: "half_marathon", label: "Half Marathon" },
  { value: "marathon", label: "Marathon" },
  { value: "ultra", label: "Ultra" },
];

const RISK_OPTIONS: { value: RiskTolerance; label: string; desc: string }[] = [
  {
    value: "conservative",
    label: "Conservative",
    desc: "Slow, steady progression. Lower injury risk.",
  },
  {
    value: "moderate",
    label: "Moderate",
    desc: "Balanced progression. Standard approach.",
  },
  {
    value: "aggressive",
    label: "Aggressive",
    desc: "Faster progression. Higher performance potential.",
  },
];

const DEFAULTS: ProfileUpdate = {
  name: "",
  age: 30,
  vo2max: null,
  vdot: null,
  weekly_mileage_base: 20,
  hr_max: null,
  hr_rest: null,
  injury_history: "",
  risk_tolerance: "moderate",
  max_weekly_increase_pct: 0.1,
  goal_distance: "general_fitness",
  goal_time_minutes: null,
  training_days_per_week: 4,
  long_run_cap_pct: 0.3,
};

const inputClass =
  "w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors";

export default function OnboardingPage() {
  const { isAuthenticated } = useAuthGuard();
  const router = useRouter();
  const { data: existing } = useProfile();
  const upsert = useUpsertProfile();
  const [form, setForm] = useState<ProfileUpdate>(DEFAULTS);

  useEffect(() => {
    if (existing) {
      setForm(existing);
    }
  }, [existing]);

  if (!isAuthenticated) return null;

  function update<K extends keyof ProfileUpdate>(
    key: K,
    value: ProfileUpdate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await upsert.mutateAsync(form);
    router.push("/dashboard");
  }

  return (
    <>
      <Navbar />
      <main className="max-w-xl mx-auto px-4 py-8 w-full">
        <h1 className="text-2xl font-bold mb-2">
          {existing ? "Update Profile" : "Athlete Profile"}
        </h1>
        <p className="text-sm text-gray-500 mb-8">
          {existing
            ? "Update your running details anytime."
            : "Tell us about your running so we can build the right plan."}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm divide-y divide-gray-100">
            {/* Section: About You */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                About You
              </h2>

              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                  Name
                </label>
                <input
                  id="name"
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="age" className="block text-sm font-medium text-gray-700 mb-1">
                  Age
                </label>
                <input
                  id="age"
                  type="number"
                  required
                  min={10}
                  max={100}
                  value={form.age || ""}
                  onChange={(e) =>
                    update("age", e.target.value ? Number(e.target.value) : 0)
                  }
                  placeholder="e.g., 30"
                  className={inputClass}
                />
              </div>
            </div>

            {/* Section: Your Running */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                Your Running
              </h2>

              <div>
                <label htmlFor="goal_distance" className="block text-sm font-medium text-gray-700 mb-1">
                  What&apos;s your running goal?
                </label>
                <select
                  id="goal_distance"
                  value={form.goal_distance}
                  onChange={(e) => update("goal_distance", e.target.value)}
                  className={inputClass}
                >
                  {GOAL_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {form.goal_distance !== "general_fitness" && (
                <div>
                  <label htmlFor="goal_time" className="block text-sm font-medium text-gray-700 mb-1">
                    Target time (minutes, optional)
                  </label>
                  <input
                    id="goal_time"
                    type="number"
                    min={1}
                    value={form.goal_time_minutes ?? ""}
                    onChange={(e) =>
                      update(
                        "goal_time_minutes",
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                    placeholder="e.g., 25 for a 25-minute 5K"
                    className={inputClass}
                  />
                </div>
              )}

              <div>
                <label htmlFor="weekly_mileage" className="block text-sm font-medium text-gray-700 mb-1">
                  Current Weekly Mileage (km)
                </label>
                <input
                  id="weekly_mileage"
                  type="number"
                  required
                  min={0}
                  step={0.1}
                  value={form.weekly_mileage_base}
                  onChange={(e) =>
                    update("weekly_mileage_base", Number(e.target.value))
                  }
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="training_days" className="block text-sm font-medium text-gray-700 mb-1">
                  Training Days Per Week
                </label>
                <input
                  id="training_days"
                  type="number"
                  required
                  min={3}
                  max={7}
                  value={form.training_days_per_week}
                  onChange={(e) =>
                    update("training_days_per_week", Number(e.target.value))
                  }
                  className={inputClass}
                />
              </div>
            </div>

            {/* Section: Preferences */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                Preferences
              </h2>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Risk Tolerance
                </label>
                <div className="space-y-2">
                  {RISK_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`flex items-start gap-3 p-3 border rounded-xl cursor-pointer transition-all ${
                        form.risk_tolerance === opt.value
                          ? "border-blue-500 bg-blue-50 shadow-sm"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <input
                        type="radio"
                        name="risk_tolerance"
                        value={opt.value}
                        checked={form.risk_tolerance === opt.value}
                        onChange={() => update("risk_tolerance", opt.value)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="font-medium text-sm">{opt.label}</div>
                        <div className="text-xs text-gray-500">{opt.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="injury_history" className="block text-sm font-medium text-gray-700 mb-1">
                  Injury History (optional)
                </label>
                <textarea
                  id="injury_history"
                  value={form.injury_history}
                  onChange={(e) => update("injury_history", e.target.value)}
                  maxLength={500}
                  rows={3}
                  placeholder="Any past or current injuries the AI should know about"
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="vdot" className="block text-sm font-medium text-gray-700 mb-1">
                  VDOT (optional)
                </label>
                <input
                  id="vdot"
                  type="number"
                  min={15}
                  max={85}
                  step={0.1}
                  value={form.vdot ?? ""}
                  onChange={(e) =>
                    update("vdot", e.target.value ? Number(e.target.value) : null)
                  }
                  placeholder="If you know your VDOT score"
                  className={inputClass}
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={upsert.isPending}
            className="w-full mt-6 px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {upsert.isPending
              ? "Saving..."
              : existing
                ? "Update Profile"
                : "Save & Continue"}
          </button>

          {upsert.isError && (
            <p className="text-red-600 text-sm text-center mt-3">
              {upsert.error instanceof Error
                ? upsert.error.message
                : "Failed to save profile"}
            </p>
          )}
        </form>
      </main>
    </>
  );
}
