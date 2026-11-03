import type { EvalSummary, JudgeReport, Label, QueueItem, Release } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  evals: () => request<EvalSummary[]>("/api/evals"),
  releases: () => request<Release[]>("/api/releases"),
  judge: (split: string) => request<JudgeReport>(`/api/judge/${split}`),
  queue: (status: "open" | "done" | "all") => request<QueueItem[]>(`/api/queue?status=${status}`),
  label: (id: string, body: { reviewer: string; label: Label; note: string }) =>
    request(`/api/queue/${encodeURIComponent(id)}/labels`, { method: "POST", body: JSON.stringify(body) }),
  pageUrl: (split: string, pkg: string, doc: string, page: number) =>
    `/api/packages/${split}/${pkg}/${doc.replace(/\.pdf$/, "")}/pages/${page}.png`,
};
