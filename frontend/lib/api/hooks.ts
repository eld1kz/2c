"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";

export const keys = {
  me: ["me"],
  position: ["position"],
  forecast: ["forecast"],
  week: (week: number) => ["forecast", "week", week],
  insights: ["insights"],
  budget: ["llm-budget"],
  pending: ["actions", "proposed"],
} as const;

export const useMe = () =>
  useQuery({ queryKey: keys.me, queryFn: async () => unwrap(await api.GET("/me")), staleTime: Infinity });

export const usePosition = () =>
  useQuery({ queryKey: keys.position, queryFn: async () => unwrap(await api.GET("/position")) });

export const useForecast = () =>
  useQuery({ queryKey: keys.forecast, queryFn: async () => unwrap(await api.GET("/forecast")) });

export const useForecastWeek = (week: number | null) =>
  useQuery({
    queryKey: keys.week(week ?? 0),
    enabled: week !== null,
    queryFn: async () => unwrap(await api.GET("/forecast/weeks/{week}", { params: { path: { week: week ?? 1 } } })),
  });

export const useInsights = () =>
  useQuery({ queryKey: keys.insights, queryFn: async () => unwrap(await api.GET("/insights")) });

export const useBudget = () =>
  useQuery({ queryKey: keys.budget, queryFn: async () => unwrap(await api.GET("/llm-budget")), refetchInterval: 60_000 });

export const usePendingActions = () =>
  useQuery({
    queryKey: keys.pending,
    queryFn: async () => unwrap(await api.GET("/actions", { params: { query: { status: "proposed" } } })),
  });

export const useRecord = (ref: string | null) =>
  useQuery({
    queryKey: ["record", ref],
    enabled: ref !== null,
    queryFn: async () => unwrap(await api.GET("/records/{ref}", { params: { path: { ref: ref ?? "" } } })),
  });

export const useRecordLabels = (refs: string[]) =>
  useQuery({
    queryKey: ["record-labels", refs],
    enabled: refs.length > 0,
    queryFn: async () => unwrap(await api.GET("/records", { params: { query: { ref: refs } } })),
    staleTime: Infinity,
  });

export const useActions = () =>
  useQuery({ queryKey: ["actions", "all"], queryFn: async () => unwrap(await api.GET("/actions")) });

/** Approve or reject. On success every view that depends on actions or cash is refreshed. */
export function useDecide() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, decision }: { id: number; decision: "approve" | "reject" }) =>
      decision === "approve"
        ? unwrap(await api.POST("/actions/{action_id}/approve", { params: { path: { action_id: id } } }))
        : unwrap(await api.POST("/actions/{action_id}/reject", { params: { path: { action_id: id } } })),
    onSettled: () => {
      for (const key of [["actions"], keys.position, keys.forecast, keys.insights]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}
