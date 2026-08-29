import { useState } from "react";
import { Card, DirectionBadge, StatusBadge, Btn, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api, Trade } from "../lib/api";
import { useApi } from "../lib/useApi";

const REFRESH_MS = 20_000;

export default function OpenTrades() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data, loading, error, reload } = useApi(() => api.openTrades(), [], REFRESH_MS);

  const trades = data?.trades || [];
  const sel = selectedId !== null ? trades.find((t) => t.id === selectedId) : null;

  if (sel) return <TradeDetail trade={sel} onBack={() => setSelectedId(null)} />;

  const pos = trades.filter((t) => t.realized_pnl_pct > 0);
  const neg = trades.filter((t) => t.realized_pnl_pct < 0);

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Open Trades</h1>
          <p className="text-[11px] text-[#555]">Active positions and live P&L tracking.</p>
        </div>
        <div className="flex gap-4">
          <Summary label="POSITIVE" value={String(pos.length)} color="text-[#22c55e]" />
          <Summary label="NEGATIVE" value={String(neg.length)} color="text-[#ef4444]" />
          <Summary label="TOTAL" value={String(trades.length)} />
        </div>
      </div>

      {loading && !data && <LoadingState label="Carregando operações abertas..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && trades.length === 0 && (
        <EmptyState title="NO OPEN TRADES" subtitle="Nenhuma posição aberta no momento." />
      )}

      <div className="space-y-3">
        {trades.map((t) => (
          <TradeCard key={t.id} trade={t} onClick={() => setSelectedId(t.id)} />
        ))}
      </div>
    </div>
  );
}

function TradeCard({ trade, onClick }: { trade: Trade; onClick: () => void }) {
  const pnlPos = trade.realized_pnl_pct >= 0;
  const tp1 = trade.targets?.[0]?.price;
  const stop = trade.stop ?? trade.initial_stop ?? 0;
  const entry = trade.entry ?? 0;
  const current = trade.last_price ?? entry;

  const range = tp1 && stop ? tp1 - stop : 0;
  const entryPct = range ? ((entry - stop) / range) * 100 : 50;
  const currentPct = range ? Math.min(100, Math.max(0, ((current - stop) / range) * 100)) : 50;

  return (
    <Card className="p-4 hover:border-[#2e2e2e] transition-colors cursor-pointer" onClick={onClick}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="font-mono text-[13px] font-600 text-[#f0f0f0]">{trade.asset}</div>
            <div className="mt-1"><DirectionBadge direction={trade.direction} /></div>
          </div>
          <div className="font-mono text-[9px] text-[#444]">{trade.strategy_name}</div>
        </div>
        <div className="text-right">
          <div className={`font-mono text-[16px] font-700 tabular-nums ${pnlPos ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
            {pnlPos ? "+" : ""}{trade.realized_pnl_pct.toFixed(2)}%
          </div>
          <div className="font-mono text-[9px] text-[#555]">{pnlPos ? "+" : ""}{trade.realized_r.toFixed(2)}R</div>
        </div>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-3">
        <LevelBox label="ENTRY" value={fmt(trade.entry)} />
        <LevelBox label="CURRENT" value={fmt(trade.last_price)} highlight />
        <LevelBox label="STOP" value={fmt(trade.stop)} danger />
        {trade.targets?.slice(0, 3).map((t, i) => (
          <LevelBox key={i} label={`TP${i + 1}`} value={fmt(t.price)} />
        ))}
      </div>

      {range > 0 && (
        <div className="mb-2">
          <div className="flex justify-between mb-1">
            <span className="font-mono text-[8px] text-[#444]">STOP</span>
            <span className="font-mono text-[8px] text-[#444]">ENTRY</span>
            <span className="font-mono text-[8px] text-[#444]">TP1</span>
          </div>
          <div className="relative h-2 bg-[#1c1c1c] rounded-full overflow-hidden">
            <div
              className="absolute h-full rounded-full"
              style={{
                left: `${entryPct}%`, width: `${Math.abs(currentPct - entryPct)}%`,
                backgroundColor: pnlPos ? "#22c55e" : "#ef4444", opacity: 0.4,
              }}
            />
            <div className="absolute top-0 bottom-0 w-px bg-[#555]" style={{ left: `${entryPct}%` }} />
            <div
              className="absolute top-0 bottom-0 w-0.5 rounded"
              style={{ left: `${currentPct}%`, backgroundColor: pnlPos ? "#22c55e" : "#ef4444" }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[9px] text-[#444]">Score: {trade.score}</span>
          <span className="font-mono text-[9px] text-[#444]">{new Date(trade.opened_at).toLocaleString()}</span>
        </div>
        <StatusBadge status={trade.status} />
      </div>
    </Card>
  );
}

function TradeDetail({ trade, onBack }: { trade: Trade; onBack: () => void }) {
  const pnlPos = trade.realized_pnl_pct >= 0;
  return (
    <div className="p-5 lg:p-6 max-w-[800px]">
      <button onClick={onBack} className="flex items-center gap-2 font-mono text-[10px] text-[#555] hover:text-[#888] mb-5">
        ← BACK TO TRADES
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="font-mono text-[22px] font-700 text-[#f0f0f0]">{trade.asset}</h1>
            <DirectionBadge direction={trade.direction} />
          </div>
          <div className="font-mono text-[10px] text-[#555]">
            Opened {new Date(trade.opened_at).toLocaleString()} · {trade.strategy_name}
          </div>
        </div>
        <div className={`font-mono text-[28px] font-700 tabular-nums ${pnlPos ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
          {pnlPos ? "+" : ""}{trade.realized_pnl_pct.toFixed(2)}%
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card className="p-4">
            <div className="font-mono text-[9px] text-[#444] tracking-widest mb-4">TARGETS</div>
            <div className="flex flex-col gap-0">
              {(trade.targets || []).map((t, i, arr) => (
                <div key={i} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`w-2.5 h-2.5 rounded-full border ${t.hit ? "bg-[#22c55e] border-[#22c55e]" : "border-[#333]"}`} />
                    {i < arr.length - 1 && <div className={`w-px flex-1 my-1 ${t.hit ? "bg-[#22c55e]/30" : "bg-[#222]"}`} style={{ minHeight: "20px" }} />}
                  </div>
                  <div className="pb-4">
                    <div className={`font-mono text-[9px] tracking-wider ${t.hit ? "text-[#22c55e]" : "text-[#444]"}`}>
                      TP{i + 1} {t.hit ? "— HIT" : ""}
                    </div>
                    <div className="font-mono text-[10px] text-[#888]">{t.price} {t.hit_at ? `· ${new Date(t.hit_at).toLocaleTimeString()}` : ""}</div>
                  </div>
                </div>
              ))}
              {(!trade.targets || trade.targets.length === 0) && (
                <span className="font-mono text-[10px] text-[#444]">Nenhum alvo registrado.</span>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <div className="font-mono text-[9px] text-[#444] tracking-widest mb-3">LEVELS</div>
            <div className="space-y-2">
              <Row label="ENTRY" value={fmt(trade.entry)} />
              <Row label="CURRENT" value={fmt(trade.last_price)} color={pnlPos ? "text-[#22c55e]" : "text-[#ef4444]"} />
              <Row label="STOP" value={fmt(trade.stop)} color="text-[#ef4444]" />
            </div>
          </Card>

          <Card className="p-4">
            <div className="font-mono text-[9px] text-[#444] tracking-widest mb-3">PERFORMANCE</div>
            <div className="space-y-2">
              <Row label="P&L" value={`${pnlPos ? "+" : ""}${trade.realized_pnl_pct.toFixed(2)}%`} color={pnlPos ? "text-[#22c55e]" : "text-[#ef4444]"} />
              <Row label="R MULTIPLE" value={`${pnlPos ? "+" : ""}${trade.realized_r.toFixed(2)}R`} color="text-[#C9A84C]" />
              <Row label="SCORE" value={String(trade.score)} />
            </div>
          </Card>

          <div className="flex flex-col gap-2">
            <Btn variant="danger" size="sm" disabled title="Ação ainda não disponível na API">CLOSE TRADE</Btn>
            <div className="font-mono text-[8px] text-[#444]">Fechar/editar operações ainda não tem endpoint na API — leitura apenas por enquanto.</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? "N/A" : String(v);
}

function LevelBox({ label, value, highlight, danger }: { label: string; value: string; highlight?: boolean; danger?: boolean }) {
  return (
    <div className="bg-[#0d0d0d] border border-[#1a1a1a] px-2 py-1.5 rounded-sm">
      <div className="font-mono text-[8px] text-[#444] mb-0.5">{label}</div>
      <div className={`font-mono text-[10px] tabular-nums ${highlight ? "text-[#f0f0f0]" : danger ? "text-[#ef4444]" : "text-[#666]"}`}>{value}</div>
    </div>
  );
}

function Summary({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-right">
      <div className={`font-mono text-[18px] font-600 ${color ?? "text-[#f0f0f0]"}`}>{value}</div>
      <div className="font-mono text-[8px] text-[#444] tracking-widest">{label}</div>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between">
      <span className="font-mono text-[9px] text-[#444]">{label}</span>
      <span className={`font-mono text-[10px] tabular-nums ${color ?? "text-[#888]"}`}>{value}</span>
    </div>
  );
}
