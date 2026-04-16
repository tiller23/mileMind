/**
 * Shared enum display maps for goal distance and risk tolerance.
 *
 * Onboarding uses the full option arrays (value + label, plus description
 * on risk) to render form selects. Dashboard, plan detail, and confirm
 * panels use the short label maps. Keeping both shapes in one file so
 * they can't drift.
 */

import type { RiskTolerance } from "./types";

export const GOAL_OPTIONS: { value: string; label: string }[] = [
  { value: "general_fitness", label: "General fitness (no specific race)" },
  { value: "5K", label: "5K" },
  { value: "10K", label: "10K" },
  { value: "half_marathon", label: "Half Marathon" },
  { value: "marathon", label: "Marathon" },
  { value: "ultra", label: "Ultra" },
];

// Short labels for display surfaces (dashboard, plan detail, confirm panel)
// where the verbose "General fitness (no specific race)" doesn't fit.
export const GOAL_LABELS: Record<string, string> = {
  general_fitness: "General Fitness",
  "5K": "5K",
  "10K": "10K",
  half_marathon: "Half Marathon",
  marathon: "Marathon",
  ultra: "Ultra",
};

// Typed as Record<RiskTolerance, string> so TypeScript forces every
// RiskTolerance variant to have a label — deleting one here is a compile
// error, not silent `undefined` at runtime.
export const RISK_LABELS: Record<RiskTolerance, string> = {
  conservative: "Conservative",
  moderate: "Moderate",
  aggressive: "Aggressive",
};

const RISK_DESCRIPTIONS: Record<RiskTolerance, string> = {
  conservative: "Build gradually. Prioritizes staying healthy.",
  moderate: "Steady progress with a good balance of challenge and recovery.",
  aggressive: "Faster progression. Higher performance potential.",
};

export const RISK_OPTIONS: { value: RiskTolerance; label: string; desc: string }[] =
  (Object.keys(RISK_LABELS) as RiskTolerance[]).map((value) => ({
    value,
    label: RISK_LABELS[value],
    desc: RISK_DESCRIPTIONS[value],
  }));
