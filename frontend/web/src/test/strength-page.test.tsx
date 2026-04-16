import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StrengthPage from "@/app/strength/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/strength",
}));

vi.mock("@/lib/hooks", () => ({
  useAuthGuard: () => ({ isLoading: false, isAuthenticated: true }),
  useUser: () => ({ data: { id: "u1", name: "Runner", email: "r@x.io", avatar_url: null, role: "user", has_invite: true, invite_request_status: null } }),
  useProfile: () => ({
    data: {
      id: "p1",
      user_id: "u1",
      name: "Runner",
      age: 30,
      weekly_mileage_base: 40,
      goal_distance: "marathon",
      injury_history: "",
      injury_tags: ["it_band"],
      current_acute_injury: false,
      current_injury_description: "",
    },
    isLoading: false,
  }),
  useStrengthPlaybook: () => ({
    data: {
      acute_injury_gate: { active: false, description: "" },
      catalog_version: "abcd1234",
      profile_summary: {},
      blocks: [
        {
          block_id: "posterior_chain",
          title: "Posterior Chain",
          rationale: "Runners need a strong backside.",
          matched_injury_tags: ["it_band"],
          exercises: [
            {
              id: "glute_bridge",
              name: "Glute Bridge",
              equipment: ["bodyweight"],
              difficulty: "beginner",
              search_query: "glute bridge form",
              why_runners: "Teaches your glutes to fire.",
              beneficial_for_user: ["it_band"],
            },
            {
              id: "single_leg_rdl",
              name: "Single-Leg RDL",
              equipment: ["dumbbells"],
              difficulty: "intermediate",
              search_query: "single leg rdl form",
              why_runners: "Balance under load.",
              beneficial_for_user: [],
            },
          ],
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StrengthPage />
    </QueryClientProvider>,
  );
}

describe("StrengthPage", () => {
  it("renders blocks and exercises", () => {
    renderPage();
    expect(screen.getByText("Strength Playbook")).toBeInTheDocument();
    expect(screen.getByText("Posterior Chain")).toBeInTheDocument();
    expect(screen.getByText("Runners need a strong backside.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Glute Bridge" })).toBeInTheDocument();
    expect(screen.getByText("bodyweight")).toBeInTheDocument();
    expect(screen.getByText("Teaches your glutes to fire.")).toBeInTheDocument();
    expect(screen.getByText(/For your: IT Band/)).toBeInTheDocument();
    expect(screen.getByText(/Tailored for: IT Band/)).toBeInTheDocument();
  });

  it("hides alternates until the user expands them", () => {
    renderPage();
    expect(screen.queryByRole("link", { name: "Single-Leg RDL" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /Show 1 more alternate/i });
    fireEvent.click(toggle);
    expect(screen.getByRole("link", { name: "Single-Leg RDL" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hide alternates/i })).toBeInTheDocument();
  });
});

describe("StrengthPage acute caution banner", () => {
  it("shows a persistent caution banner AND the playbook when acute injury is flagged", async () => {
    vi.resetModules();
    vi.doMock("@/lib/hooks", () => ({
      useAuthGuard: () => ({ isLoading: false, isAuthenticated: true }),
      useUser: () => ({ data: { id: "u1", name: "R", email: "r@x", avatar_url: null, role: "user", has_invite: true, invite_request_status: null } }),
      useProfile: () => ({
        data: {
          id: "p1",
          user_id: "u1",
          name: "R",
          injury_tags: ["it_band"],
          current_acute_injury: true,
          current_injury_description: "knee tweak",
        },
        isLoading: false,
      }),
      useStrengthPlaybook: () => ({
        data: {
          acute_injury_gate: { active: true, description: "knee tweak" },
          catalog_version: "v",
          profile_summary: {},
          blocks: [
            {
              block_id: "posterior_chain",
              title: "Posterior Chain",
              rationale: "Runners need a strong backside.",
              matched_injury_tags: ["it_band"],
              exercises: [
                {
                  id: "glute_bridge",
                  name: "Glute Bridge",
                  equipment: ["bodyweight"],
                  difficulty: "beginner",
                  search_query: "glute bridge form",
                  why_runners: "Teaches your glutes to fire.",
                  beneficial_for_user: ["it_band"],
                },
              ],
            },
          ],
        },
        isLoading: false,
        error: null,
      }),
    }));
    const Mod = await import("@/app/strength/page");
    const Page = Mod.default;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Page />
      </QueryClientProvider>,
    );
    // Banner copy: action-framed, not blame-framed.
    expect(
      screen.getByText(/See a physical therapist before starting/i),
    ).toBeInTheDocument();
    // User's own note is reflected back.
    expect(screen.getByText(/knee tweak/i)).toBeInTheDocument();
    // Update-status CTA is the single action; NO dismiss button.
    expect(
      screen.getByRole("link", { name: /update injury status/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /i understand/i }),
    ).not.toBeInTheDocument();
    // Blocks still render alongside the banner.
    expect(screen.getByText("Posterior Chain")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Glute Bridge" })).toBeInTheDocument();
  });
});
