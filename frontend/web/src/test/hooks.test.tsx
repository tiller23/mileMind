import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock API module
vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:8000/api/v1",
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  },
  auth: {
    me: vi.fn(),
  },
  profile: {
    get: vi.fn(),
    upsert: vi.fn(),
  },
  plans: {
    list: vi.fn(),
    get: vi.fn(),
    debug: vi.fn(),
    archive: vi.fn(),
    generate: vi.fn(),
  },
}));

import { auth, profile, ApiError } from "@/lib/api";
import { useUser, useAuthGuard, useProfile, usePlans } from "@/lib/hooks";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPush.mockClear();
});

describe("useUser", () => {
  it("returns user data on success", async () => {
    const user = { id: "1", email: "test@example.com", name: "Test", avatar_url: null };
    vi.mocked(auth.me).mockResolvedValue(user);

    const { result } = renderHook(() => useUser(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(user);
  });

  it("returns error when not authenticated", async () => {
    vi.mocked(auth.me).mockRejectedValue(new ApiError(401, "Unauthorized"));

    const { result } = renderHook(() => useUser(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useAuthGuard", () => {
  it("redirects to /login on auth failure", async () => {
    vi.mocked(auth.me).mockRejectedValue(new ApiError(401, "Unauthorized"));

    renderHook(() => useAuthGuard(), { wrapper: createWrapper() });

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });

  it("does not redirect when authenticated", async () => {
    const user = { id: "1", email: "test@example.com", name: "Test", avatar_url: null };
    vi.mocked(auth.me).mockResolvedValue(user);

    const { result } = renderHook(() => useAuthGuard(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
    expect(mockPush).not.toHaveBeenCalled();
  });
});

describe("useProfile", () => {
  it("returns profile data on success", async () => {
    const profileData = { id: "1", user_id: "1", name: "Runner", age: 30 };
    vi.mocked(profile.get).mockResolvedValue(profileData as ReturnType<typeof profile.get> extends Promise<infer T> ? T : never);

    const { result } = renderHook(() => useProfile(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(profileData);
  });

  it("returns null data on 404 instead of erroring", async () => {
    vi.mocked(profile.get).mockRejectedValue(new ApiError(404, "Not found"));

    const { result } = renderHook(() => useProfile(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it("throws on non-404 errors", async () => {
    vi.mocked(profile.get).mockRejectedValue(new ApiError(500, "Server error"));

    const { result } = renderHook(() => useProfile(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
