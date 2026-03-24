import { describe, expect, it } from "vitest";
import type {
  ChangeType,
  DecisionLogEntry,
  JobDetailResponse,
  JobStatus,
  PlanDetail,
  PlanSummary,
  ProfileResponse,
  ProfileUpdate,
  ProgressEvent,
  ProgressEventType,
  ReviewerScores,
  RiskTolerance,
} from "@/lib/types";

describe("TypeScript types", () => {
  it("ProfileUpdate accepts valid data", () => {
    const profile: ProfileUpdate = {
      name: "Test Runner",
      age: 30,
      vo2max: 45.0,
      vdot: 40.0,
      weekly_mileage_base: 30,
      hr_max: 185,
      hr_rest: 55,
      injury_history: "",
      risk_tolerance: "moderate",
      max_weekly_increase_pct: 0.1,
      goal_distance: "5K",
      goal_time_minutes: 25,
      training_days_per_week: 4,
      long_run_cap_pct: 0.3,
      preferred_units: "imperial",
    };
    expect(profile.name).toBe("Test Runner");
  });

  it("RiskTolerance type accepts valid values", () => {
    const values: RiskTolerance[] = [
      "conservative",
      "moderate",
      "aggressive",
    ];
    expect(values).toHaveLength(3);
  });

  it("ReviewerScores has correct shape", () => {
    const scores: ReviewerScores = {
      safety: 90,
      progression: 85,
      specificity: 80,
      feasibility: 82,
    };
    expect(scores.safety).toBe(90);
  });

  it("PlanSummary matches expected structure", () => {
    const plan: PlanSummary = {
      id: "abc-123",
      approved: true,
      status: "active",
      scores: { safety: 90, progression: 85, specificity: 80, feasibility: 82 },
      goal_event: "10K",
      week_count: 12,
      created_at: "2026-03-20T00:00:00Z",
    };
    expect(plan.approved).toBe(true);
  });

  it("JobStatus type accepts valid statuses", () => {
    const statuses: JobStatus[] = ["pending", "running", "complete", "failed"];
    expect(statuses).toHaveLength(4);
  });

  it("ProgressEvent has correct shape", () => {
    const event: ProgressEvent = {
      event_type: "planner_started",
      message: "Planner starting",
      data: { attempt: 1 },
      timestamp: "2026-03-20T00:00:00Z",
      sequence: 0,
    };
    expect(event.event_type).toBe("planner_started");
  });

  it("ChangeType accepts valid values", () => {
    const types: ChangeType[] = ["full", "adaptation", "tweak"];
    expect(types).toHaveLength(3);
  });

  it("DecisionLogEntry has correct shape", () => {
    const entry: DecisionLogEntry = {
      iteration: 1,
      timestamp: "2026-03-20T00:00:00Z",
      outcome: "approved",
      scores: { safety: 90, progression: 85, specificity: 80, feasibility: 82 },
      critique: "Good plan",
      issues: [],
      planner_input_tokens: 500,
      planner_output_tokens: 300,
      reviewer_input_tokens: 200,
      reviewer_output_tokens: 100,
      planner_tool_calls: 5,
      reviewer_tool_calls: 2,
    };
    expect(entry.outcome).toBe("approved");
  });

  it("ProfileResponse extends ProfileUpdate", () => {
    const response: ProfileResponse = {
      id: "abc-123",
      user_id: "user-456",
      name: "Test",
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
      preferred_units: "metric",
      created_at: "2026-03-20T00:00:00Z",
      updated_at: "2026-03-20T00:00:00Z",
    };
    expect(response.id).toBe("abc-123");
  });

  it("PlanDetail has all required fields", () => {
    const detail: PlanDetail = {
      id: "plan-1",
      user_id: "user-1",
      athlete_snapshot: { name: "Test" },
      plan_data: { text: "Week 1: run" },
      decision_log: [],
      scores: null,
      approved: false,
      status: "active",
      total_tokens: 1000,
      estimated_cost_usd: 0.5,
      created_at: "2026-03-20T00:00:00Z",
    };
    expect(detail.total_tokens).toBe(1000);
  });

  it("JobDetailResponse has all required fields", () => {
    const job: JobDetailResponse = {
      job_id: "job-1",
      status: "complete",
      plan_id: "plan-1",
      error: null,
      progress: [],
      created_at: "2026-03-20T00:00:00Z",
      completed_at: "2026-03-20T00:01:00Z",
    };
    expect(job.status).toBe("complete");
  });

  it("ProgressEventType covers all backend event types", () => {
    const types: ProgressEventType[] = [
      "job_started",
      "planner_started",
      "planner_complete",
      "validation_result",
      "reviewer_started",
      "reviewer_complete",
      "retry",
      "token_budget",
      "job_complete",
      "job_failed",
    ];
    expect(types).toHaveLength(10);
  });
});
