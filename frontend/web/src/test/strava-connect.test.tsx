import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StravaConnect } from "@/components/StravaConnect";

// Mock the API module
vi.mock("@/lib/api", () => ({
  strava: {
    connect: vi.fn(),
    status: vi.fn(),
    sync: vi.fn(),
    disconnect: vi.fn(),
    activities: vi.fn(),
  },
  API_BASE: "http://test",
  ApiError: class extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail);
    }
  },
}));

// Mock hooks
const mockStravaStatus = vi.fn();
const mockStravaSync = vi.fn();
const mockStravaDisconnect = vi.fn();

vi.mock("@/lib/hooks", () => ({
  useStravaStatus: () => mockStravaStatus(),
  useStravaSync: () => mockStravaSync(),
  useStravaDisconnect: () => mockStravaDisconnect(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("StravaConnect", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStravaSync.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    mockStravaDisconnect.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
  });

  it("renders connect button when not connected", () => {
    mockStravaStatus.mockReturnValue({
      data: { connected: false, athlete_id: null, last_sync: null },
      isLoading: false,
    });

    render(<StravaConnect />, { wrapper });

    expect(screen.getByText("Connect Strava")).toBeTruthy();
    expect(screen.getByText("Connect with Strava")).toBeTruthy();
    expect(screen.getByText(/Powered by Strava/)).toBeTruthy();
  });

  it("renders connected state with sync and disconnect", () => {
    mockStravaStatus.mockReturnValue({
      data: {
        connected: true,
        athlete_id: 12345,
        last_sync: "2026-03-20T10:00:00Z",
      },
      isLoading: false,
    });

    render(<StravaConnect />, { wrapper });

    expect(screen.getByText("Strava Connected")).toBeTruthy();
    expect(screen.getByText("Sync Now")).toBeTruthy();
    expect(screen.getByText("Disconnect")).toBeTruthy();
  });

  it("shows loading state as null", () => {
    mockStravaStatus.mockReturnValue({
      data: undefined,
      isLoading: true,
    });

    const { container } = render(<StravaConnect />, { wrapper });
    expect(container.innerHTML).toBe("");
  });

  it("shows confirm dialog on disconnect click", () => {
    mockStravaStatus.mockReturnValue({
      data: { connected: true, athlete_id: 12345, last_sync: null },
      isLoading: false,
    });

    render(<StravaConnect />, { wrapper });

    fireEvent.click(screen.getByText("Disconnect"));
    expect(screen.getByText("Confirm")).toBeTruthy();
    expect(screen.getByText("Cancel")).toBeTruthy();
  });

  it("calls sync mutate on Sync Now click", () => {
    const mutateFn = vi.fn();
    mockStravaStatus.mockReturnValue({
      data: { connected: true, athlete_id: 12345, last_sync: null },
      isLoading: false,
    });
    mockStravaSync.mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    });

    render(<StravaConnect />, { wrapper });

    fireEvent.click(screen.getByText("Sync Now"));
    expect(mutateFn).toHaveBeenCalledOnce();
  });

  it("displays Powered by Strava attribution when connected", () => {
    mockStravaStatus.mockReturnValue({
      data: { connected: true, athlete_id: 12345, last_sync: null },
      isLoading: false,
    });

    render(<StravaConnect />, { wrapper });

    expect(screen.getByText("Powered by Strava")).toBeTruthy();
  });
});
