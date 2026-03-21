/**
 * TypeScript types matching backend Pydantic schemas.
 * Keep in sync with backend/src/api/schemas.py.
 */

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export type RiskTolerance = "conservative" | "moderate" | "aggressive";

export interface ProfileUpdate {
  name: string;
  age: number;
  vo2max: number | null;
  vdot: number | null;
  weekly_mileage_base: number;
  hr_max: number | null;
  hr_rest: number | null;
  injury_history: string;
  risk_tolerance: RiskTolerance;
  max_weekly_increase_pct: number;
  goal_distance: string;
  goal_time_minutes: number | null;
  training_days_per_week: number;
  long_run_cap_pct: number;
}

export interface ProfileResponse extends ProfileUpdate {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Plans
// ---------------------------------------------------------------------------

export interface ReviewerScores {
  safety: number;
  progression: number;
  specificity: number;
  feasibility: number;
  overall?: number;
}

export interface PlanSummary {
  id: string;
  approved: boolean;
  status: string;
  scores: ReviewerScores | null;
  created_at: string;
}

export interface PlanDetail {
  id: string;
  user_id: string;
  athlete_snapshot: Record<string, unknown>;
  plan_data: Record<string, unknown>;
  decision_log: DecisionLogEntry[];
  scores: ReviewerScores | null;
  approved: boolean;
  status: string;
  total_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
}

export interface DecisionLogEntry {
  iteration: number;
  timestamp: string;
  outcome: "approved" | "rejected" | "error";
  scores: ReviewerScores | null;
  critique: string;
  issues: string[];
  planner_input_tokens: number;
  planner_output_tokens: number;
  reviewer_input_tokens: number;
  reviewer_output_tokens: number;
  planner_tool_calls: number;
  reviewer_tool_calls: number;
}

export interface PlanDebug {
  id: string;
  decision_log: DecisionLogEntry[];
  scores: ReviewerScores | null;
  approved: boolean;
  total_tokens: number;
  estimated_cost_usd: number;
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export type JobStatus = "pending" | "running" | "complete" | "failed";

export interface JobResponse {
  job_id: string;
  status: JobStatus;
}

export interface JobDetailResponse {
  job_id: string;
  status: JobStatus;
  plan_id: string | null;
  error: string | null;
  progress: ProgressEvent[];
  created_at: string;
  completed_at: string | null;
}

export type ProgressEventType =
  | "job_started"
  | "planner_started"
  | "planner_complete"
  | "validation_result"
  | "reviewer_started"
  | "reviewer_complete"
  | "retry"
  | "token_budget"
  | "job_complete"
  | "job_failed";

export interface ProgressEvent {
  event_type: ProgressEventType;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
  sequence: number;
}

// ---------------------------------------------------------------------------
// Plan Generation
// ---------------------------------------------------------------------------

export type ChangeType = "full" | "adaptation" | "tweak";

export interface PlanGenerateRequest {
  change_type: ChangeType;
}

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

export interface MessageResponse {
  detail: string;
}
