export type ResearchStatus = "queued" | "collecting" | "analysing" | "reviewing" | "completed" | "failed";

export interface Evidence {
  id: string;
  source_server: string;
  tool_name: string;
  request_params: Record<string, unknown>;
  response_sha256: string;
  excerpt: string;
  captured_at: string | null;
}

export interface Research {
  id: string;
  symbol: string;
  resolved_name: string | null;
  as_of_date: string | null;
  status: ResearchStatus;
  created_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface ResearchDetail extends Research {
  report_markdown: string | null;
  evidence: Evidence[];
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init.headers },
    ...init,
  });
  if (!response.ok) {
    let message = "请求失败";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (response.status === 422) message = "输入信息有误，请检查股票和截至日期。";
    } catch {
      // keep a safe generic error
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  me: () => request<{ username: string }>("/auth/me"),
  login: (username: string, password: string) =>
    request<void>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  listResearches: (symbol?: string, asOf?: string) => {
    const query = new URLSearchParams();
    if (symbol) query.set("symbol", symbol);
    if (asOf) query.set("as_of", asOf);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<Research[]>(`/researches${suffix}`);
  },
  createResearch: (symbol: string, asOf?: string) =>
    request<Research>("/researches", {
      method: "POST",
      body: JSON.stringify({ symbol, as_of: asOf || null }),
    }),
  getResearch: (id: string) => request<ResearchDetail>(`/researches/${encodeURIComponent(id)}`),
  markdownUrl: (id: string) => `/api/researches/${encodeURIComponent(id)}/markdown`,
};
