/**
 * React Query hooks for MileMind API.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, auth, jobs, plans, profile } from "./api";
import type {
  PlanGenerateRequest,
  PlanUpdateStartDate,
  ProfileResponse,
  ProfileUpdate,
} from "./types";

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function useUser() {
  return useQuery({
    queryKey: ["user"],
    queryFn: () => auth.me(),
    retry: false,
  });
}

/** Redirect to /login if the user is not authenticated. */
export function useAuthGuard() {
  const { error, isLoading } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && error) {
      router.push("/login");
    }
  }, [isLoading, error, router]);

  return { isLoading, isAuthenticated: !isLoading && !error };
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

/**
 * Fetch the user's profile. Returns `data: null` on 404 (no profile yet)
 * instead of throwing, so callers can distinguish "no profile" from errors.
 */
export function useProfile() {
  return useQuery<ProfileResponse | null>({
    queryKey: ["profile"],
    queryFn: async () => {
      try {
        return await profile.get();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    retry: false,
  });
}

export function useUpsertProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProfileUpdate) => profile.upsert(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Plans
// ---------------------------------------------------------------------------

export function usePlans() {
  return useQuery({
    queryKey: ["plans"],
    queryFn: () => plans.list(),
    staleTime: 60_000,
  });
}

export function usePlan(planId: string) {
  return useQuery({
    queryKey: ["plan", planId],
    queryFn: () => plans.get(planId),
    enabled: !!planId,
    staleTime: Infinity,
  });
}

export function usePlanDebug(planId: string) {
  return useQuery({
    queryKey: ["plan-debug", planId],
    queryFn: () => plans.debug(planId),
    enabled: !!planId,
    staleTime: Infinity,
  });
}

export function useGeneratePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (opts: PlanGenerateRequest = { change_type: "full" }) =>
      plans.generate(opts),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

export function useUpdatePlanStartDate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, data }: { planId: string; data: PlanUpdateStartDate }) =>
      plans.updateStartDate(planId, data),
    onSuccess: (_result, { planId }) => {
      queryClient.invalidateQueries({ queryKey: ["plan", planId] });
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

export function useActiveJob() {
  return useQuery({
    queryKey: ["active-job"],
    queryFn: () => jobs.active(),
    refetchInterval: false,
    staleTime: 0,
  });
}

export function useArchivePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => plans.archive(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}
