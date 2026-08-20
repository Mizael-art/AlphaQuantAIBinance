"use client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "aqx_strategy_lab_token";

export type StrategyVersion = {
  id: number;
  version_label: string;
  prompt_raw: string;
  status: "VALID" | "INVALID" | "UNSUPPORTED_CONDITION";
  errors: string[];
  unsupported_conditions: string[];
  author: string | null;
  change_note: string | null;
  created_at: string;
  is_current?: boolean;
};

export type Strategy = {
  id: number;
  name: string;
  mode: string;
  status: "ACTIVE" | "INACTIVE" | "ARCHIVED";
  current_version: StrategyVersion | null;
  version_count: number;
  is_runnable: boolean;
  created_at: string;
  updated_at: string;
};

export type TestResult = {
  runnable: boolean;
  status?: string;
  errors?: string[];
  unsupported_conditions?: string[];
  asset?: string;
  timeframe?: string;
  matched?: boolean;
  direction?: "LONG" | "SHORT" | null;
  progress?: number;
  conditions_met?: string[];
  conditions_missing?: string[];
  entry?: number | null;
  stop?: number | null;
  notes?: string;
  last_close?: number | null;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authedFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    cache: "no-store",
  });
  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, "sessão expirada — faça login novamente");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || "usuário ou senha inválidos");
  }
  const data = await res.json();
  setToken(data.access_token);
}

export function listStrategies() {
  return authedFetch<{ strategies: Strategy[] }>("/strategies");
}

export function getStrategyVersions(id: number) {
  return authedFetch<{ versions: StrategyVersion[] }>(`/strategies/${id}/versions`);
}

export function createStrategy(input: { name: string; prompt: string; mode: string; active: boolean }) {
  return authedFetch<Strategy>("/strategies", { method: "POST", body: JSON.stringify(input) });
}

export function updateStrategy(id: number, input: { prompt?: string; mode?: string; change_note?: string }) {
  return authedFetch<Strategy>(`/strategies/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function activateStrategy(id: number) {
  return authedFetch<Strategy>(`/strategies/${id}/activate`, { method: "POST" });
}

export function deactivateStrategy(id: number) {
  return authedFetch<Strategy>(`/strategies/${id}/deactivate`, { method: "POST" });
}

export function archiveStrategy(id: number) {
  return authedFetch<Strategy>(`/strategies/${id}`, { method: "DELETE" });
}

export function duplicateStrategy(id: number) {
  return authedFetch<Strategy>(`/strategies/${id}/duplicate`, { method: "POST" });
}

export function testStrategy(id: number, asset: string, timeframe: string) {
  return authedFetch<TestResult>(`/strategies/${id}/test`, {
    method: "POST",
    body: JSON.stringify({ asset, timeframe }),
  });
}

export type BacktestResult = {
  period: { start: string; end: string; candles: number };
  stats: {
    trades: number;
    win_rate: number;
    payoff: number;
    profit_factor: number;
    expectancy: number;
    max_drawdown: number;
  };
};

export function runBacktest(id: number, asset: string, timeframe: string, lookback: number) {
  return authedFetch<BacktestResult>(`/strategies/${id}/backtest`, {
    method: "POST",
    body: JSON.stringify({ asset, timeframe, lookback }),
  });
}

export { ApiError };
