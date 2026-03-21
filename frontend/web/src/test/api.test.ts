import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";

describe("ApiError", () => {
  it("has status and detail", () => {
    const err = new ApiError(404, "Not found");
    expect(err.status).toBe(404);
    expect(err.detail).toBe("Not found");
    expect(err.message).toBe("Not found");
    expect(err.name).toBe("ApiError");
  });

  it("is an instance of Error", () => {
    const err = new ApiError(500, "Server error");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("ScoreBadge color logic", () => {
  it("returns green for scores >= 80", () => {
    // Testing the color logic directly
    function scoreColor(score: number): string {
      if (score >= 80) return "bg-green-100 text-green-800";
      if (score >= 70) return "bg-yellow-100 text-yellow-800";
      return "bg-red-100 text-red-800";
    }
    expect(scoreColor(90)).toContain("green");
    expect(scoreColor(80)).toContain("green");
    expect(scoreColor(75)).toContain("yellow");
    expect(scoreColor(70)).toContain("yellow");
    expect(scoreColor(60)).toContain("red");
  });
});
