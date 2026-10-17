"use client";

import { useQuery } from "@tanstack/react-query";

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
