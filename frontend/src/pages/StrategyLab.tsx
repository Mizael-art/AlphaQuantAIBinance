import { useState } from "react";
import { Card, Btn, StatusBadge, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api, Strategy, getToken, setToken, clearToken, ApiError } from "../lib/api";
import { useApi } from "../lib/useApi";

export default function StrategyLab() {
  const [loggedIn, setLoggedIn] = useState(!!getToken());

  if (!loggedIn) return <LoginGate onSuccess={() => setLoggedIn(true)} />;

  return <StrategyList onLogout={() => { clearToken(); setLoggedIn(false); }} />;
}

function LoginGate({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(username, password);
      setToken(res.access_token);
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? "Usuário ou senha inválidos." : "Falha ao conectar com a API.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-5 lg:p-6 flex items-center justify-center min-h-[60vh]">
      <Card className="p-6 w-full max-w-sm">
        <div className="font-mono text-[12px] text-[#C9A84C] tracking-widest mb-1">STRATEGY LAB</div>
        <div className="font-mono text-[10px] text-[#555] mb-5">Área protegida — login administrativo necessário.</div>
        <form onSubmit={handleLogin} className="space-y-3">
          <input
            type="text"
            placeholder="usuário"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full bg-[#0d0d0d] border border-[#1e1e1e] rounded-sm px-3 py-2 font-mono text-[11px] text-[#f0f0f0] focus:outline-none focus:border-[#C9A84C]/40"
          />
          <input
            type="password"
            placeholder="senha"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-[#0d0d0d] border border-[#1e1e1e] rounded-sm px-3 py-2 font-mono text-[11px] text-[#f0f0f0] focus:outline-none focus:border-[#C9A84C]/40"
          />
          {error && <div className="font-mono text-[10px] text-[#ef4444]">{error}</div>}
          <Btn variant="gold" size="sm" className="w-full justify-center">
            {loading ? "ENTRANDO..." : "ENTRAR"}
          </Btn>
        </form>
      </Card>
    </div>
  );
}

function StrategyList({ onLogout }: { onLogout: () => void }) {
  const { data, loading, error, reload } = useApi(() => api.strategies(), []);
  const [expanded, setExpanded] = useState<number | null>(null);
  const strategies = data?.strategies || [];

  const isAuthError = error?.includes("Autenticação");

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Strategy Lab</h1>
          <p className="text-[11px] text-[#555]">Estratégias em prompt cadastradas no sistema.</p>
        </div>
        <Btn variant="ghost" size="xs" onClick={onLogout}>LOGOUT</Btn>
      </div>

      {loading && !data && <LoadingState label="Carregando estratégias..." />}
      {error && (
        <ErrorState
          message={isAuthError ? "Sessão expirada — faça login de novo." : error}
          onRetry={isAuthError ? onLogout : reload}
        />
      )}
      {!loading && !error && strategies.length === 0 && <EmptyState title="NO STRATEGIES" />}

      <div className="space-y-3">
        {strategies.map((s) => (
          <StrategyCard key={s.id} strategy={s} expanded={expanded === s.id} onToggle={() => setExpanded(expanded === s.id ? null : s.id)} />
        ))}
      </div>
    </div>
  );
}

function StrategyCard({ strategy, expanded, onToggle }: { strategy: Strategy; expanded: boolean; onToggle: () => void }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-mono text-[13px] font-600 text-[#f0f0f0]">{strategy.name}</div>
          <div className="font-mono text-[9px] text-[#555] mt-0.5">
            {strategy.mode} · {strategy.version_count} version{strategy.version_count > 1 ? "s" : ""} · {strategy.is_runnable ? "RUNNABLE" : "NOT RUNNABLE"}
          </div>
        </div>
        <StatusBadge status={strategy.status} />
      </div>

      <button
        onClick={onToggle}
        className="font-mono text-[9px] text-[#C9A84C] border border-[#C9A84C]/20 px-2 py-1 rounded-sm hover:bg-[#C9A84C]/10 transition-colors mb-2"
      >
        {expanded ? "OCULTAR DEFINIÇÃO" : "VER DEFINIÇÃO"}
      </button>

      {expanded && strategy.current_version && (
        <pre className="bg-[#0d0d0d] border border-[#1a1a1a] rounded-sm p-3 font-mono text-[10px] text-[#888] whitespace-pre-wrap overflow-x-auto mb-3">
          {strategy.current_version.prompt_raw}
        </pre>
      )}

      <div className="flex gap-2 flex-wrap pt-2 border-t border-[#1a1a1a]">
        {["EDIT", "TEST", "BACKTEST", "DUPLICATE", "DISABLE", "DELETE"].map((action) => (
          <Btn key={action} variant="ghost" size="xs" disabled title="Ação com endpoint real na API, mas ainda sem formulário neste frontend">
            {action}
          </Btn>
        ))}
      </div>
    </Card>
  );
}
