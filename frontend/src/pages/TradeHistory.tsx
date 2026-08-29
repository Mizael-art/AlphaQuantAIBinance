import { useState } from "react";
import { Card, FilterChips, DirectionBadge, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";

const FILTERS = ["ALL", "WINS", "LOSSES", "LONG", "SHORT"];

export default function TradeHistory() {
  const [filter, setFilter] = useState("ALL");
  const { data, loading, error, reload } = useApi(() => api.closedTrades({ limit: 100 }), []);
  const { data: perf } = useApi(() => api.performance(), []);

  const history = data?.trades || [];

  let trades = history;
  if (filter === "WINS") trades = trades.filter((t) => t.result === "WIN" || t.result === "PARTIAL_WIN");
  if (filter === "LOSSES") trades = trades.filter((t) => t.result === "LOSS" || t.result === "PARTIAL_LOSS");
  if (filter === "LONG") trades = trades.filter((t) => t.direction === "LONG");
  if (filter === "SHORT") trades = trades.filter((t) => t.direction === "SHORT");

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Trade History</h1>
          <p className="text-[11px] text-[#555]">Closed trades and performance record.</p>
        </div>
      </div>

      {/* Stats row — /trades/performance real */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        {[
          { l: "TOTAL TRADES", v: perf ? String(perf.closed_trades) : "…" },
          { l: "WIN RATE", v: perf ? `${(perf.win_rate * 100).toFixed(0)}%` : "…", c: "text-[#22c55e]" },
          { l: "PROFIT FACTOR", v: perf?.profit_factor != null ? perf.profit_factor.toFixed(2) : "N/A" },
          { l: "EXPECTANCY", v: perf ? `${perf.average_r >= 0 ? "+" : ""}${perf.average_r.toFixed(2)}R` : "…", c: "text-[#C9A84C]" },
          { l: "WORST TRADE", v: perf?.worst_trade_r != null ? `${perf.worst_trade_r.toFixed(2)}R` : "N/A", c: "text-[#ef4444]" },
        ].map(({ l, v, c }) => (
          <Card key={l} className="px-4 py-3">
            <div className="font-mono text-[8px] text-[#444] tracking-widest mb-1">{l}</div>
            <div className={`font-mono text-[18px] font-600 tabular-nums ${c ?? "text-[#f0f0f0]"}`}>{v}</div>
          </Card>
        ))}
      </div>

      <div className="mb-4">
        <FilterChips options={FILTERS} active={filter} onSelect={setFilter} />
      </div>

      {loading && !data && <LoadingState label="Carregando histórico..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && trades.length === 0 && (
        <EmptyState title="NO TRADE HISTORY" subtitle="Nenhuma operação fechada ainda." />
      )}

      {trades.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="border-b border-[#1e1e1e]">
                {["OPENED", "CLOSED", "ASSET", "DIR", "STRATEGY", "ENTRY", "LAST PRICE", "RESULT", "R"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-mono text-[9px] text-[#444] tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => {
                const win = t.result === "WIN" || t.result === "PARTIAL_WIN";
                return (
                  <tr key={t.id} className={`border-b border-[#111] hover:bg-[#151515] transition-colors ${i % 2 === 0 ? "" : "bg-[#0d0d0d]"}`}>
                    <td className="px-3 py-2.5 font-mono text-[9px] text-[#555]">{new Date(t.opened_at).toLocaleDateString()}</td>
                    <td className="px-3 py-2.5 font-mono text-[9px] text-[#555]">{t.closed_at ? new Date(t.closed_at).toLocaleDateString() : "N/A"}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px] font-600 text-[#f0f0f0]">{t.asset}</td>
                    <td className="px-3 py-2.5"><DirectionBadge direction={t.direction} /></td>
                    <td className="px-3 py-2.5 font-mono text-[9px] text-[#555]">{t.strategy_name}</td>
                    <td className="px-3 py-2.5 font-mono text-[10px] tabular-nums text-[#888]">{t.entry ?? "N/A"}</td>
                    <td className="px-3 py-2.5 font-mono text-[10px] tabular-nums text-[#888]">{t.last_price ?? "N/A"}</td>
                    <td className="px-3 py-2.5">
                      <span className={`font-mono text-[11px] font-600 tabular-nums ${win ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
                        {t.realized_pnl_pct >= 0 ? "+" : ""}{t.realized_pnl_pct.toFixed(2)}%
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`font-mono text-[10px] tabular-nums ${win ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
                        {t.realized_r >= 0 ? "+" : ""}{t.realized_r.toFixed(2)}R
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
