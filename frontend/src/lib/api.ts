/**
 * Cliente da API real do AlphaQuant X (substitui os dados mock usados
 * no design original — seção 40 do master prompt: "todos os
 * componentes devem ser preparados para receber dados reais da API").
 *
 * Nunca inventa dado: se um endpoint falhar ou não trouxer um campo,
 * quem consome isso deve mostrar N/A / DATA UNAVAILABLE (ver
 * EmptyState/ErrorState em ui.tsx), nunca preencher com valor fixo.
 */

export const API_BASE_URL =
  (import.meta as any).env?.VITE_API_URL || "https://alphaquantx-api.onrender.com";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "aqx_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers || {}),
      },
    });
  } catch (e) {
    // rede indisponível / CORS / instância dormindo (Render free) — nunca
    // finge sucesso, propaga pro caller decidir o ErrorState certo.
    throw new ApiError("Não foi possível conectar à API. O serviço pode estar hibernando (plano Free do Render) — tente novamente em alguns segundos.");
  }
  if (res.status === 401 || res.status === 403) {
    throw new ApiError("Autenticação necessária ou expirada. Faça login novamente.", res.status);
  }
  if (!res.ok) {
    throw new ApiError(`API respondeu ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------
// Tipos — espelham exatamente o que os routers da API devolvem hoje.
// ---------------------------------------------------------------------

export interface Opportunity {
  id: number;
  asset: string;
  timeframe: string;
  playbook: string;
  direction: "LONG" | "SHORT";
  status: "FORMATION" | "CONFIRMED" | "INVALIDATED" | string;
  decision: "ENTRAR" | "ESPERAR" | "REPROVAR" | null;
  score: number;
  confidence: string;
  progress: number;
  entry: number | null;
  stop: number | null;
  tp1: number | null;
  tp2: number | null;
  tp3: number | null;
  rr: number | null;
  created_at: string;
  updated_at: string;
  invalidated_at: string | null;
}

export interface Summary {
  window: string;
  opportunities_analyzed: number;
  score_ge_70: number;
  score_ge_80: number;
  score_ge_90: number;
  confirmed: number;
  future_formation: number;
  invalidated: number;
  scanner_status: string;
  scanner_last_heartbeat: string | null;
}

export interface HealthService {
  status: string;
  last_heartbeat: string | null;
  latency_ms: number | null;
}

export interface Health {
  status: string;
  checked_at: string;
  services: Record<string, HealthService>;
}

// ---------------------------------------------------------------------
// Chamadas
// ---------------------------------------------------------------------

export interface Trade {
  id: number;
  opportunity_id: number;
  asset: string;
  timeframe: string;
  direction: "LONG" | "SHORT";
  strategy_name: string;
  score: number;
  entry: number | null;
  initial_stop: number | null;
  stop: number | null;
  targets: { price: number; exit_pct: number; rr: number; hit: boolean; hit_at: string | null; hit_price: number | null }[];
  status: string;
  result: string | null;
  remaining_pct: number;
  realized_pnl_pct: number;
  realized_r: number;
  last_price: number | null;
  opened_at: string;
  closed_at: string | null;
}

export interface PerformanceSummary {
  open_trades: number;
  closed_trades: number;
  win_rate: number;
  average_r: number;
  total_r: number;
  best_trade_r: number | null;
  worst_trade_r: number | null;
  profit_factor: number | null;
}

export interface Playbook {
  id: number;
  name: string;
  version: number;
  tier: string;
  minimum_score: number;
  minimum_rr: number;
  status: string;
}

export interface Strategy {
  id: number;
  name: string;
  mode: string;
  status: string;
  current_version: {
    id: number;
    version_label: string;
    prompt_raw: string;
    status: string;
    errors: string[] | null;
    unsupported_conditions: string[] | null;
    created_at: string;
    author: string | null;
    change_note: string | null;
  } | null;
  version_count: number;
  is_runnable: boolean;
  created_at: string;
}

export const api = {
  summary: () => apiFetch<Summary>("/summary"),

  health: () => apiFetch<Health>("/health"),

  login: (username: string, password: string) =>
    apiFetch<{ access_token: string; token_type: string; expires_in: number }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  opportunities: (params?: { status?: string; asset?: string; playbook?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.asset) qs.set("asset", params.asset);
    if (params?.playbook) qs.set("playbook", params.playbook);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<{ count: number; opportunities: Opportunity[] }>(`/opportunities${suffix}`);
  },

  opportunityDetail: (id: number) =>
    apiFetch<Opportunity & { audit_snapshot: any; evidence: { category: string; evidence: string; score: number; timestamp: string }[] }>(
      `/opportunities/${id}`,
    ),

  strategies: () => apiFetch<{ strategies: Strategy[] }>("/strategies"),

  playbooks: () => apiFetch<{ count: number; playbooks: Playbook[] }>("/playbooks"),

  openTrades: () => apiFetch<{ count: number; trades: Trade[] }>("/trades/open"),

  closedTrades: (params?: { asset?: string; strategy_name?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.asset) qs.set("asset", params.asset);
    if (params?.strategy_name) qs.set("strategy_name", params.strategy_name);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<{ count: number; trades: Trade[] }>(`/trades/closed${suffix}`);
  },

  performance: (strategy_name?: string) =>
    apiFetch<PerformanceSummary>(`/trades/performance${strategy_name ? `?strategy_name=${encodeURIComponent(strategy_name)}` : ""}`),

  marketData: (symbol: string, timeframe: string = "1h") =>
    apiFetch<any>(`/market-data/${symbol}?timeframe=${timeframe}`),
};
