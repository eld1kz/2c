"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ScenarioInput } from "@/lib/scenarios";

import { api, ApiError, detailOf, type Schemas, unwrap } from "./client";

export const keys = {
  me: ["me"],
  position: ["position"],
  forecast: ["forecast"],
  week: (week: number) => ["forecast", "week", week],
  insights: ["insights"],
  budget: ["llm-budget"],
  pending: ["actions", "proposed"],
  today: ["today"],
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

/** Before/after forecast for a scenario. A simulation: it writes nothing, so it is cached like a read. */
export const useWhatIf = (scenarios: ScenarioInput[], enabled = true) =>
  useQuery({
    queryKey: ["whatif", JSON.stringify(scenarios)],
    enabled: enabled && scenarios.length > 0,
    queryFn: async () => unwrap(await api.POST("/whatif", { body: { scenarios } })),
    retry: false,
  });

/** Financing options for the base gap (no scenarios) or the gap left after the scenarios. Writes nothing. */
export const useFinancing = (scenarios: ScenarioInput[], enabled = true) =>
  useQuery({
    queryKey: ["financing", JSON.stringify(scenarios)],
    enabled,
    queryFn: async () => unwrap(await api.POST("/financing", { body: { scenarios } })),
    retry: false,
  });

export const useCfoMemo = () =>
  useQuery({ queryKey: ["memo"], queryFn: async () => unwrap(await api.GET("/memo")) });

/** Writes this week's memo with the assistant (spends AI budget once; the result is cached server-side). */
export function useGenerateMemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/memo")),
    onSuccess: (data) => {
      if (data.memo?.generated_at) queryClient.setQueryData(["memo"], data);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.budget }),
  });
}

export const useTeam = () =>
  useQuery({ queryKey: ["team"], queryFn: async () => unwrap(await api.GET("/team")) });

export const useToday = () =>
  useQuery({ queryKey: keys.today, queryFn: async () => unwrap(await api.GET("/today")) });

/** Drafts and proposes a Today decision's action (no AI); a human still approves it. */
export function usePrepare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (insightId: number) =>
      unwrap(await api.POST("/today/decisions/{insight_id}/prepare", { params: { path: { insight_id: insightId } } })),
    onSettled: () => {
      for (const key of [keys.today, keys.pending]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

/** "Can I afford it?": one agent turn (spends AI budget); the verdict comes from the engine. */
export function useAfford() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (question: string) => unwrap(await api.POST("/afford", { body: { question } })),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.budget }),
  });
}

export const useMonthClose = () =>
  useQuery({ queryKey: ["paperwork", "month-close"], queryFn: async () => unwrap(await api.GET("/paperwork/month-close")) });

export const useBankPack = () =>
  useQuery({ queryKey: ["paperwork", "bank-pack"], queryFn: async () => unwrap(await api.GET("/paperwork/bank-pack")) });

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
      for (const key of [["actions"], keys.position, keys.forecast, keys.insights, keys.today]) {
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

export function usePlaidSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Schemas["UploadOut"]> => {
      const response = await fetch("/api/backend/bank-feed/plaid/sync", { method: "POST" });
      const body = await response.json().catch(() => undefined);
      if (!response.ok) throw new ApiError(response.status, detailOf(body));
      return body;
    },
    onSuccess: () => void queryClient.invalidateQueries(),
  });
}

export function useResetDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/demo/reset")),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
