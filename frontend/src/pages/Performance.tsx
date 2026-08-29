import { Card, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";

export default function Performance() {
  const { data: perf, loading, error, reload } = useApi(() => api.performance(), []);
  const { data: playbooksData } = useApi(() => api.playbooks(), []);

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Performance</h1>
          <p className="text-[11px] text-[#555]">Estatísticas reais calculadas a partir do histórico de trades.</p>
        </div>
      </div>

      {loading && !perf && <LoadingState label="Calculando performance..." />}
      {error && <ErrorState message={error} onRetry={reload} />}

      {perf && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
            {[
              { l: "OPEN TRADES", v: String(perf.open_trades) },
              { l: "CLOSED TRADES", v: String(perf.closed_trades) },
              { l: "WIN RATE", v: `${(perf.win_rate * 100).toFixed(1)}%`, c: "text-[#22c55e]" },
              { l: "PROFIT FACTOR", v: perf.profit_factor != null ? perf.profit_factor.toFixed(2) : "N/A", c: "text-[#C9A84C]" },
              { l: "EXPECTANCY", v: `${perf.average_r >= 0 ? "+" : ""}${perf.average_r.toFixed(2)}R`, c: "text-[#C9A84C]" },
              { l: "TOTAL R", v: `${perf.total_r >= 0 ? "+" : ""}${perf.total_r.toFixed(2)}R`, c: perf.total_r >= 0 ? "text-[#22c55e]" : "text-[#ef4444]" },
            ].map(({ l, v, c }) => (
              <Card key={l} className="px-3 py-3">
                <div className="font-mono text-[8px] text-[#444] tracking-widest mb-1">{l}</div>
                <div className={`font-mono text-[14px] font-600 tabular-nums ${c ?? "text-[#f0f0f0]"}`}>{v}</div>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 mb-6">
            <Card className="px-4 py-3">
              <div className="font-mono text-[8px] text-[#444] tracking-widest mb-1">BEST TRADE</div>
              <div className="font-mono text-[16px] font-600 text-[#22c55e] tabular-nums">
                {perf.best_trade_r != null ? `+${perf.best_trade_r.toFixed(2)}R` : "N/A"}
              </div>
            </Card>
            <Card className="px-4 py-3">
              <div className="font-mono text-[8px] text-[#444] tracking-widest mb-1">WORST TRADE</div>
              <div className="font-mono text-[16px] font-600 text-[#ef4444] tabular-nums">
                {perf.worst_trade_r != null ? `${perf.worst_trade_r.toFixed(2)}R` : "N/A"}
              </div>
            </Card>
          </div>

          <Card className="p-4 mb-5">
            <div className="font-mono text-[10px] text-[#555] tracking-widest mb-1">EQUITY CURVE</div>
            <div className="font-mono text-[10px] text-[#444]">
              Ainda não há endpoint de série histórica (capital ao longo do tempo) na API — nada é desenhado aqui até existir dado real pra isso.
            </div>
          </Card>

          <PerformanceByStrategy />
        </>
      )}
    </div>
  );
}

function PerformanceByStrategy() {
  const { data: playbooksData, loading, error } = useApi(() => api.playbooks(), []);
  const playbooks = playbooksData?.playbooks || [];

  return (
    <Card className="overflow-x-auto">
      <div className="px-4 py-3 border-b border-[#1e1e1e]">
        <div className="font-mono text-[10px] text-[#555] tracking-widest">PERFORMANCE BY STRATEGY</div>
      </div>
      {loading && <div className="p-4"><LoadingState label="Carregando..." /></div>}
      {error && <div className="p-4"><ErrorState message={error} /></div>}
      {!loading && !error && playbooks.length === 0 && <div className="p-4"><EmptyState title="NO PLAYBOOKS" /></div>}
      {playbooks.length > 0 && (
        <table className="w-full min-w-[600px]">
          <thead>
            <tr className="border-b border-[#1e1e1e]">
              {["STRATEGY", "TRADES", "WIN RATE", "EXPECTANCY", "PROFIT FACTOR"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-mono text-[9px] text-[#444] tracking-widest">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {playbooks.map((p, i) => (
              <StrategyRow key={p.id} name={p.name} alt={i % 2 !== 0} />
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function StrategyRow({ name, alt }: { name: string; alt: boolean }) {
  const { data: perf } = useApi(() => api.performance(name), [name]);
  return (
    <tr className={`border-b border-[#111] hover:bg-[#151515] transition-colors ${alt ? "bg-[#0d0d0d]" : ""}`}>
      <td className="px-4 py-2.5 font-mono text-[11px] text-[#888]">{name}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] text-[#888] tabular-nums">{perf ? perf.closed_trades : "…"}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums text-[#22c55e]">{perf ? `${(perf.win_rate * 100).toFixed(0)}%` : "…"}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums text-[#C9A84C]">{perf ? `${perf.average_r >= 0 ? "+" : ""}${perf.average_r.toFixed(2)}R` : "…"}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums text-[#888]">{perf?.profit_factor != null ? perf.profit_factor.toFixed(2) : "N/A"}</td>
    </tr>
  );
}
