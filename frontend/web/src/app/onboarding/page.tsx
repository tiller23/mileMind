"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { useProfile, useUpsertProfile } from "@/lib/hooks";
import type { ProfileUpdate, RiskTolerance } from "@/lib/types";

const GOAL_DISTANCES = ["5K", "10K", "half_marathon", "marathon", "ultra"];

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
  goal_distance: "5K",
  goal_time_minutes: null,
  training_days_per_week: 4,
  long_run_cap_pct: 0.3,
};

export default function OnboardingPage() {
  const router = useRouter();
  const { data: existing } = useProfile();
  const upsert = useUpsertProfile();

  const [form, setForm] = useState<ProfileUpdate>(DEFAULTS);

  // Sync form state when existing profile loads
  useEffect(() => {
    if (existing) {
      setForm(existing);
    }
  }, [existing]);

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
        <h1 className="text-2xl font-bold mb-6">
          {existing ? "Update Profile" : "Athlete Profile"}
        </h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Name */}
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Age */}
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
              value={form.age}
              onChange={(e) => update("age", Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Goal Distance */}
          <div>
            <label htmlFor="goal_distance" className="block text-sm font-medium text-gray-700 mb-1">
              Goal Distance
            </label>
            <select
              id="goal_distance"
              value={form.goal_distance}
              onChange={(e) => update("goal_distance", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {GOAL_DISTANCES.map((d) => (
                <option key={d} value={d}>
                  {d.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>

          {/* Goal Time */}
          <div>
            <label htmlFor="goal_time" className="block text-sm font-medium text-gray-700 mb-1">
              Goal Time (minutes, optional)
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Weekly Mileage */}
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Training Days */}
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Risk Tolerance */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Risk Tolerance
            </label>
            <div className="space-y-2">
              {RISK_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                    form.risk_tolerance === opt.value
                      ? "border-blue-500 bg-blue-50"
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

          {/* Injury History */}
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* VDOT */}
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
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={upsert.isPending}
            className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {upsert.isPending
              ? "Saving..."
              : existing
                ? "Update Profile"
                : "Save & Continue"}
          </button>

          {upsert.isError && (
            <p className="text-red-600 text-sm text-center">
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
