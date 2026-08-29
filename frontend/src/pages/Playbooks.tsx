import { useState } from "react";
import { Card, StatusBadge, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api, Playbook, PerformanceSummary } from "../lib/api";
import { useApi } from "../lib/useApi";

export default function Playbooks() {
  const { data, loading, error, reload } = useApi(() => api.playbooks(), []);
  const [expanded, setExpanded] = useState<number | null>(null);

  const playbooks = data?.playbooks || [];

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Playbooks</h1>
          <p className="text-[11px] text-[#555]">Estratégias cadastradas no motor de scan.</p>
        </div>
        <span className="font-mono text-[10px] text-[#555]">{playbooks.length} playbooks</span>
      </div>

      {loading && !data && <LoadingState label="Carregando playbooks..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && playbooks.length === 0 && <EmptyState title="NO PLAYBOOKS" />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {playbooks.map((p) => (
          <PlaybookCard
            key={p.id}
            playbook={p}
            expanded={expanded === p.id}
            onToggle={() => setExpanded(expanded === p.id ? null : p.id)}
          />
        ))}
      </div>
    </div>
  );
}

function PlaybookCard({ playbook, expanded, onToggle }: { playbook: Playbook; expanded: boolean; onToggle: () => void }) {
  const { data: perf, loading, error } = useApi(
    () => (expanded ? api.performance(playbook.name) : Promise.resolve(null as unknown as PerformanceSummary)),
    [expanded, playbook.name],
  );

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-mono text-[13px] font-600 text-[#f0f0f0]">{playbook.name}</div>
          <div className="font-mono text-[9px] text-[#555] mt-0.5">v{playbook.version} · {playbook.tier}</div>
        </div>
        <StatusBadge status={playbook.status} />
      </div>

      <div className="grid grid-cols-2 gap-3 my-3 pt-3 border-t border-[#1a1a1a]">
        <div>
          <div className="font-mono text-[8px] text-[#444]">MIN SCORE</div>
          <div className="font-mono text-[11px] text-[#888]">{playbook.minimum_score}</div>
        </div>
        <div>
          <div className="font-mono text-[8px] text-[#444]">MIN RR</div>
          <div className="font-mono text-[11px] text-[#888]">1:{playbook.minimum_rr.toFixed(1)}</div>
        </div>
      </div>

      <button
        onClick={onToggle}
        className="font-mono text-[9px] text-[#C9A84C] border border-[#C9A84C]/20 px-2 py-1 rounded-sm hover:bg-[#C9A84C]/10 transition-colors"
      >
        {expanded ? "OCULTAR PERFORMANCE" : "VER PERFORMANCE"}
      </button>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-[#1a1a1a]">
          {loading && <span className="font-mono text-[9px] text-[#555]">Carregando...</span>}
          {error && <span className="font-mono text-[9px] text-[#ef4444]">{error}</span>}
          {perf && (
            <div className="grid grid-cols-3 gap-2">
              <Stat l="TRADES" v={String(perf.closed_trades)} />
              <Stat l="WIN RATE" v={`${(perf.win_rate * 100).toFixed(0)}%`} c="text-[#22c55e]" />
              <Stat l="EXPECTANCY" v={`${perf.average_r >= 0 ? "+" : ""}${perf.average_r.toFixed(2)}R`} c="text-[#C9A84C]" />
              <Stat l="PROFIT FACTOR" v={perf.profit_factor != null ? perf.profit_factor.toFixed(2) : "N/A"} />
              <Stat l="BEST" v={perf.best_trade_r != null ? `${perf.best_trade_r.toFixed(2)}R` : "N/A"} c="text-[#22c55e]" />
              <Stat l="WORST" v={perf.worst_trade_r != null ? `${perf.worst_trade_r.toFixed(2)}R` : "N/A"} c="text-[#ef4444]" />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Stat({ l, v, c }: { l: string; v: string; c?: string }) {
  return (
    <div>
      <div className="font-mono text-[8px] text-[#444] tracking-widest">{l}</div>
      <div className={`font-mono text-[11px] tabular-nums ${c ?? "text-[#888]"}`}>{v}</div>
    </div>
  );
}
