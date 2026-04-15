import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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
  });
});

describe("StrengthPage acute gate", () => {
  beforeEach(() => {
    vi.resetModules();
    window.sessionStorage.clear();
  });

  it("shows the PT gate when acute injury is flagged", async () => {
    vi.doMock("@/lib/hooks", () => ({
      useAuthGuard: () => ({ isLoading: false, isAuthenticated: true }),
      useUser: () => ({ data: { id: "u1", name: "R", email: "r@x", avatar_url: null, role: "user", has_invite: true, invite_request_status: null } }),
      useProfile: () => ({
        data: {
          id: "p1",
          user_id: "u1",
          name: "R",
          injury_tags: [],
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
              rationale: "x",
              matched_injury_tags: [],
              exercises: [],
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
    expect(
      screen.getByText(/You flagged a current injury/i),
    ).toBeInTheDocument();
    const ack = screen.getByRole("button", {
      name: /i understand/i,
    });
    fireEvent.click(ack);
    await waitFor(() => {
      expect(screen.queryByText(/You flagged a current injury/i)).not.toBeInTheDocument();
    });
  });
});
