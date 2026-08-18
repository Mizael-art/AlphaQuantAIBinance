const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type OpportunitySummary = {
  id: number;
  asset: string;
  timeframe: string;
  playbook: string;
  direction: "LONG" | "SHORT";
  status: "FORMATION" | "CONFIRMED" | "INVALIDATED" | "EXPIRED";
  decision: "ENTRAR" | "ESPERAR" | "REPROVAR" | null;
  score: number;
  confidence: "BAIXA" | "MODERADA" | "ALTA";
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
};

export type EvidenceRow = {
  category: string;
  evidence: string;
  score: number;
  timestamp: string;
};

export type OpportunityDetail = OpportunitySummary & {
  audit_snapshot: Record<string, unknown>;
  evidence: EvidenceRow[];
};

export type Playbook = {
  id: number;
  name: string;
  version: string;
  tier: string;
  minimum_score: number;
  minimum_rr: number;
  status: "ACTIVE" | "VALIDATING" | "EXPERIMENTAL" | "SUSPENDED" | "RETIRED";
};

export type Summary = {
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
};

export type HealthResponse = {
  status: string;
  checked_at: string;
  services: Record<string, { status: string; last_heartbeat: string | null; latency_ms: number | null }>;
};

async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
    }
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Falha ao buscar ${path}: HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function listOpportunities(params?: { status?: string; playbook?: string; asset?: string }) {
  return apiFetch<{ count: number; opportunities: OpportunitySummary[] }>("/opportunities", params);
}

export function getOpportunity(id: number) {
  return apiFetch<OpportunityDetail>(`/opportunities/${id}`);
}

export function listPlaybooks() {
  return apiFetch<{ count: number; playbooks: Playbook[] }>("/playbooks");
}

export function getSummary() {
  return apiFetch<Summary>("/summary");
}

export function getHealth() {
  return apiFetch<HealthResponse>("/health");
}
