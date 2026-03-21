import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { scoreColor } from "@/components/ScoreBadge";

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

describe("scoreColor", () => {
  it("returns green for scores >= 80", () => {
    expect(scoreColor(90)).toContain("green");
    expect(scoreColor(80)).toContain("green");
  });

  it("returns yellow for scores 70-79", () => {
    expect(scoreColor(75)).toContain("yellow");
    expect(scoreColor(70)).toContain("yellow");
  });

  it("returns red for scores < 70", () => {
    expect(scoreColor(60)).toContain("red");
    expect(scoreColor(0)).toContain("red");
  });
});
