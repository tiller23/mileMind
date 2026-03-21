import type { ReviewerScores } from "@/lib/types";

const LABELS: Record<keyof ReviewerScores, string> = {
  safety: "Safety",
  progression: "Progression",
  specificity: "Specificity",
  feasibility: "Feasibility",
  overall: "Overall",
};

export function scoreColor(score: number): string {
  if (score >= 80) return "bg-green-100 text-green-800";
  if (score >= 70) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-800";
}

interface ScoreBadgeProps {
  dimension: keyof ReviewerScores;
  score: number;
}

export function ScoreBadge({ dimension, score }: ScoreBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${scoreColor(score)}`}
    >
      {LABELS[dimension]} {score}
    </span>
  );
}

interface ScoreBadgeGroupProps {
  scores: ReviewerScores;
}

export function ScoreBadgeGroup({ scores }: ScoreBadgeGroupProps) {
  const dimensions = (
    ["safety", "progression", "specificity", "feasibility"] as const
  ).filter((d) => scores[d] != null);

  return (
    <div className="flex flex-wrap gap-1.5">
      {dimensions.map((d) => (
        <ScoreBadge key={d} dimension={d} score={scores[d]} />
      ))}
    </div>
  );
}
