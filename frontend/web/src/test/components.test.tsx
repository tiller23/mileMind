import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScoreBadge, ScoreBadgeGroup } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import type { ReviewerScores } from "@/lib/types";

describe("ScoreBadge", () => {
  it("renders dimension label and score", () => {
    render(<ScoreBadge dimension="safety" score={85} />);
    expect(screen.getByText("Safety 85")).toBeInTheDocument();
  });

  it("applies green class for high scores", () => {
    render(<ScoreBadge dimension="safety" score={90} />);
    const badge = screen.getByText("Safety 90");
    expect(badge.className).toContain("green");
  });

  it("applies yellow class for medium scores", () => {
    render(<ScoreBadge dimension="progression" score={75} />);
    const badge = screen.getByText("Progression 75");
    expect(badge.className).toContain("yellow");
  });

  it("applies red class for low scores", () => {
    render(<ScoreBadge dimension="feasibility" score={50} />);
    const badge = screen.getByText("Feasibility 50");
    expect(badge.className).toContain("red");
  });
});

describe("ScoreBadgeGroup", () => {
  it("renders all four dimensions", () => {
    const scores: ReviewerScores = {
      safety: 85,
      progression: 78,
      specificity: 90,
      feasibility: 65,
    };
    render(<ScoreBadgeGroup scores={scores} />);
    expect(screen.getByText("Safety 85")).toBeInTheDocument();
    expect(screen.getByText("Progression 78")).toBeInTheDocument();
    expect(screen.getByText("Specificity 90")).toBeInTheDocument();
    expect(screen.getByText("Feasibility 65")).toBeInTheDocument();
  });

  it("skips null dimensions", () => {
    const scores: ReviewerScores = {
      safety: 85,
      progression: 78,
      specificity: 90,
      feasibility: 65,
      overall: undefined,
    };
    render(<ScoreBadgeGroup scores={scores} />);
    expect(screen.queryByText(/Overall/)).not.toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders with default label from variant", () => {
    render(<StatusBadge variant="approved" />);
    expect(screen.getByText("approved")).toBeInTheDocument();
  });

  it("renders with custom label", () => {
    render(<StatusBadge variant="approved" label="Approved" />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("applies green styling for approved", () => {
    render(<StatusBadge variant="approved" label="OK" />);
    expect(screen.getByText("OK").className).toContain("green");
  });

  it("applies yellow styling for unapproved", () => {
    render(<StatusBadge variant="unapproved" label="Pending" />);
    expect(screen.getByText("Pending").className).toContain("yellow");
  });

  it("applies red styling for error", () => {
    render(<StatusBadge variant="error" label="Error" />);
    expect(screen.getByText("Error").className).toContain("red");
  });

  it("applies pill shape when pill prop is true", () => {
    render(<StatusBadge variant="active" label="Active" pill />);
    expect(screen.getByText("Active").className).toContain("rounded-full");
  });

  it("applies default shape without pill prop", () => {
    render(<StatusBadge variant="active" label="Active" />);
    const el = screen.getByText("Active");
    expect(el.className).toContain("rounded");
    expect(el.className).not.toContain("rounded-full");
  });
});
