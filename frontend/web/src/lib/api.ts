/**
 * API client for MileMind backend.
 *
 * Uses fetch with credentials (httpOnly cookies) for auth.
 * All responses are typed. Errors throw ApiError.
 */

import type {
  JobDetailResponse,
  JobResponse,
  MessageResponse,
  PlanDebug,
  PlanDetail,
  PlanGenerateRequest,
  PlanSummary,
  PlanUpdateStartDate,
  ProfileResponse,
  ProfileUpdate,
  StravaSyncResponse,
  StravaStatusResponse,
  UserResponse,
  WorkoutLogResponse,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

let refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const { headers, ...rest } = options;
  const res = await fetch(url, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(headers as Record<string, string>),
    },
  });

  if (res.status === 401 && path !== "/auth/refresh") {
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      return request<T>(path, options);
    }
  }

  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // response wasn't JSON
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const auth = {
  /** Get the current authenticated user. */
  me(): Promise<UserResponse> {
    return request<UserResponse>("/auth/me");
  },

  /** Refresh the access token using the refresh cookie. */
  refresh(): Promise<{ access_token: string; token_type: string }> {
    return request("/auth/refresh", { method: "POST" });
  },

  /** Log out (clears cookies). */
  logout(): Promise<void> {
    return request("/auth/logout", { method: "POST" });
  },
};

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export const profile = {
  /** Get the current user's athlete profile. */
  get(): Promise<ProfileResponse> {
    return request<ProfileResponse>("/profile");
  },

  /** Create or update the athlete profile. */
  upsert(data: ProfileUpdate): Promise<ProfileResponse> {
    return request<ProfileResponse>("/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },
};

// ---------------------------------------------------------------------------
// Plans
// ---------------------------------------------------------------------------

export const plans = {
  /** List all plans for the current user. */
  list(): Promise<PlanSummary[]> {
    return request<PlanSummary[]>("/plans");
  },

  /** Get full plan detail. */
  get(planId: string): Promise<PlanDetail> {
    return request<PlanDetail>(`/plans/${encodeURIComponent(planId)}`);
  },

  /** Get plan debug view. */
  debug(planId: string): Promise<PlanDebug> {
    return request<PlanDebug>(`/plans/${encodeURIComponent(planId)}/debug`);
  },

  /** Update plan start date. */
  updateStartDate(planId: string, data: PlanUpdateStartDate): Promise<PlanDetail> {
    return request<PlanDetail>(`/plans/${encodeURIComponent(planId)}/start-date`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  /** Archive a plan. */
  archive(planId: string): Promise<{ detail: string }> {
    return request(`/plans/${encodeURIComponent(planId)}/archive`, { method: "POST" });
  },

  /** Trigger plan generation. Returns job ID. */
  generate(
    opts: PlanGenerateRequest = { change_type: "full" },
  ): Promise<JobResponse> {
    return request<JobResponse>("/plans/generate", {
      method: "POST",
      body: JSON.stringify(opts),
    });
  },
};

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export const jobs = {
  /** Get the current user's active (running) job, or null. */
  active(): Promise<JobDetailResponse | null> {
    return request<JobDetailResponse | null>("/jobs/active");
  },

  /** Get job status. */
  get(jobId: string): Promise<JobDetailResponse> {
    return request<JobDetailResponse>(`/jobs/${encodeURIComponent(jobId)}`);
  },

  /** Connect to SSE stream for a job. Returns an EventSource. */
  stream(jobId: string): EventSource {
    const url = `${API_BASE}/jobs/${encodeURIComponent(jobId)}/stream`;
    return new EventSource(url, { withCredentials: true });
  },
};

// ---------------------------------------------------------------------------
// Strava
// ---------------------------------------------------------------------------

export const strava = {
  /** Get Strava OAuth connect URL. */
  connect(): Promise<{ auth_url: string; state: string; state_token: string }> {
    return request("/strava/connect");
  },

  /** Exchange Strava authorization code. */
  callback(data: {
    code: string;
    state: string;
  }): Promise<{ connected: boolean; athlete_id: number }> {
    return request("/strava/callback", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Get Strava connection status. */
  status(): Promise<StravaStatusResponse> {
    return request<StravaStatusResponse>("/strava/status");
  },

  /** Trigger Strava activity sync. */
  sync(): Promise<StravaSyncResponse> {
    return request<StravaSyncResponse>("/strava/sync", { method: "POST" });
  },

  /** Disconnect Strava. */
  disconnect(): Promise<MessageResponse> {
    return request<MessageResponse>("/strava/disconnect", { method: "POST" });
  },

  /** List imported Strava activities. */
  activities(limit = 50, offset = 0): Promise<WorkoutLogResponse[]> {
    return request<WorkoutLogResponse[]>(
      `/strava/activities?limit=${limit}&offset=${offset}`,
    );
  },
};
