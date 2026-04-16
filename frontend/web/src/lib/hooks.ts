/**
 * React Query hooks for MileMind API.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, auth, demo, invite, jobs, plans, profile, strava, strength } from "./api";
import type {
  InviteRequestAdminResponse,
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
      // Drop the cached strength playbook entirely — next visit to
      // /strength starts fresh (loading spinner → accurate data).
      // invalidateQueries alone caused a visible flash of stale blocks
      // because the 5-minute staleTime kept old data on screen while the
      // background refetch ran.
      queryClient.removeQueries({ queryKey: ["strength-playbook"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Invite
// ---------------------------------------------------------------------------

export function useRequestInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => invite.request(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user"] });
    },
  });
}

export function useAdminInviteRequests(statusFilter?: string) {
  return useQuery({
    queryKey: ["admin-invite-requests", statusFilter],
    queryFn: () => invite.adminList(statusFilter),
    staleTime: 10_000,
  });
}

export function useApproveInviteRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => invite.approve(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-invite-requests"] });
    },
  });
}

export function useDenyInviteRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => invite.deny(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-invite-requests"] });
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

export function usePlan(planId: string | undefined) {
  return useQuery({
    queryKey: ["plan", planId],
    queryFn: () => plans.get(planId!),
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

// ---------------------------------------------------------------------------
// Strava
// ---------------------------------------------------------------------------

export function useStravaStatus() {
  return useQuery({
    queryKey: ["strava-status"],
    queryFn: () => strava.status(),
    staleTime: 60_000,
  });
}

export function useStravaSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => strava.sync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strava-status"] });
      queryClient.invalidateQueries({ queryKey: ["strava-activities"] });
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

export function useStravaDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => strava.disconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strava-status"] });
      queryClient.invalidateQueries({ queryKey: ["strava-activities"] });
    },
  });
}

export function useStravaActivities(limit = 50) {
  return useQuery({
    queryKey: ["strava-activities", limit],
    queryFn: () => strava.activities(limit),
    enabled: limit > 0,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Demo (public, no auth)
// ---------------------------------------------------------------------------

export function useDemoPlans() {
  return useQuery({
    queryKey: ["demo-plans"],
    queryFn: () => demo.plans(),
    staleTime: Infinity,
  });
}

export function useDemoPlan(planId: string | undefined) {
  return useQuery({
    queryKey: ["demo-plan", planId],
    queryFn: () => demo.plan(planId!),
    enabled: !!planId,
    staleTime: Infinity,
  });
}

export function useDemoPlanDebug(planId: string | undefined) {
  return useQuery({
    queryKey: ["demo-plan-debug", planId],
    queryFn: () => demo.debug(planId!),
    enabled: !!planId,
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------------------
// Strength Playbook
// ---------------------------------------------------------------------------

export function useStrengthPlaybook() {
  return useQuery({
    queryKey: ["strength-playbook"],
    queryFn: () => strength.playbook(),
    staleTime: 5 * 60_000,
  });
}
