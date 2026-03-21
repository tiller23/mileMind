/**
 * React Query hooks for MileMind API.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { auth, plans, profile } from "./api";
import type {
  PlanGenerateRequest,
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

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => profile.get(),
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

export function useArchivePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => plans.archive(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}
