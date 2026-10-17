"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, detailOf, type Schemas, unwrap } from "./client";

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

const AUDIT_PAGE = 500;
const AUDIT_MAX_PAGES = 20;

/** Every audit event of this business, newest first (the API pages oldest-first by seq). */
export const useAuditEvents = () =>
  useQuery({
    queryKey: ["audit"],
    queryFn: async () => {
      const all: Schemas["AuditEventOut"][] = [];
      let after = 0;
      for (let page = 0; page < AUDIT_MAX_PAGES; page++) {
        const rows = unwrap(await api.GET("/audit", { params: { query: { after_seq: after, limit: AUDIT_PAGE } } }));
        all.push(...rows);
        if (rows.length < AUDIT_PAGE) break;
        after = rows[rows.length - 1].seq;
      }
      return all.reverse();
    },
  });

export function useVerifyChain() {
  return useMutation({ mutationFn: async () => unwrap(await api.GET("/audit/verify")) });
}

export const useTransactions = (needsReview: boolean, pages: number) =>
  useQuery({
    queryKey: ["transactions", needsReview, pages],
    queryFn: async () => {
      const rows: Schemas["TransactionOut"][] = [];
      let hasMore = false;
      for (let page = 0; page < pages; page++) {
        const out = unwrap(
          await api.GET("/transactions", { params: { query: { needs_review: needsReview || undefined, offset: rows.length } } }),
        );
        rows.push(...out.rows);
        hasMore = out.has_more;
        if (!hasMore) break;
      }
      return { rows, hasMore };
    },
    placeholderData: (previous) => previous,
  });

export function useRecategorize() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, category }: { id: number; category: Schemas["Category"] }) =>
      unwrap(await api.POST("/transactions/{transaction_id}/category", { params: { path: { transaction_id: id } }, body: { category } })),
    onSuccess: () => {
      for (const key of [["transactions"], keys.forecast, keys.insights, ["record"]]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<Schemas["UploadOut"]> => {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/backend/upload", { method: "POST", body: form });
      const body = await response.json().catch(() => undefined);
      if (!response.ok) throw new ApiError(response.status, detailOf(body));
      return body;
    },
    onSuccess: () => void queryClient.invalidateQueries(),
  });
}
