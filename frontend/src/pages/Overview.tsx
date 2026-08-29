import { Page } from "../App";
import {
  Card, MetricCard, Badge, DirectionBadge, ScoreBadge,
  StatusBadge, Btn, LoadingState, ErrorState, EmptyState,
} from "../components/ui";
import { api, Opportunity } from "../lib/api";
import { useApi } from "../lib/useApi";

const REFRESH_MS = 30_000;

export default function Overview({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const { data: summary, loading: loadingSummary, error: errorSummary, reload: reloadSummary } =
    useApi(() => api.summary(), [], REFRESH_MS);
  const { data: oppsData, loading: loadingOpps, error: errorOpps, reload: reloadOpps } =
    useApi(() => api.opportunities({ limit: 8 }), [], REFRESH_MS);
  const { data: health } = useApi(() => api.health(), [], REFRESH_MS);
  const { data: openTradesData } = useApi(() => api.openTrades(), [], REFRESH_MS);

  const scannerOnline = summary?.scanner_status === "ONLINE";
  const workerHealth = health?.services?.["worker"];

  const topOpps = (oppsData?.opportunities || [])
    .filter((o) => o.status !== "INVALIDATED")
    .sort((a, b) => b.score - a.score)
    .slice(0, 4);

  return (
    <div className="p-5 lg:p-6 max-w-[1400px] space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0] tracking-wide">Market Intelligence</h1>
          <p className="text-[11px] text-[#555]">Real-time market scanning and opportunity detection.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full pulse-dot ${scannerOnline ? "bg-[#22c55e]" : "bg-[#ef4444]"}`} />
          <span className={`font-mono text-[10px] tracking-wider ${scannerOnline ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
            {summary?.scanner_status ?? "UNKNOWN"}
          </span>
        </div>
      </div>

      {errorSummary && <ErrorState message={errorSummary} onRetry={reloadSummary} />}

      {!errorSummary && (
        <>
          {/* Top metric cards — dados reais do /summary (janela de 24h) */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard
              label="Scanner"
              value={<span className={scannerOnline ? "text-[#22c55e]" : "text-[#ef4444]"}>{summary?.scanner_status ?? "…"}</span>}
              highlight
            />
            <MetricCard label="Analyzed (24h)" value={summary ? String(summary.opportunities_analyzed) : "…"} sub="opportunities" />
            <MetricCard label="Score ≥70" value={summary ? String(summary.score_ge_70) : "…"} />
            <MetricCard label="Score ≥90" value={summary ? String(summary.score_ge_90) : "…"} />
            <MetricCard
              label="Confirmed"
              value={<span className="text-[#C9A84C]">{summary ? summary.confirmed : "…"}</span>}
              highlight
            />
            <MetricCard label="Open Trades" value={openTradesData ? String(openTradesData.count) : "…"} />
          </div>

          {/* Scanner Status + System */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="p-4">
              <div className="text-[10px] font-mono text-[#555] tracking-widest mb-3">OPPORTUNITIES (24H)</div>
              <div className="space-y-2">
                {[
                  { label: "Analyzed", value: summary?.opportunities_analyzed },
                  { label: "Score ≥70", value: summary?.score_ge_70 },
                  { label: "Score ≥80", value: summary?.score_ge_80 },
                  { label: "Score ≥90", value: summary?.score_ge_90 },
                  { label: "Confirmed", value: summary?.confirmed },
                  { label: "Formation", value: summary?.future_formation },
                  { label: "Invalidated", value: summary?.invalidated },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-[#555]">{label}</span>
                    <span className="font-mono text-[10px] text-[#888] tabular-nums">{value ?? "N/A"}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4">
              <div className="text-[10px] font-mono text-[#555] tracking-widest mb-3">SCANNER / WORKER</div>
              <div className="space-y-2">
                {[
                  { label: "Status", value: summary?.scanner_status ?? "UNKNOWN", ok: scannerOnline },
                  {
                    label: "Last Heartbeat",
                    value: summary?.scanner_last_heartbeat ? new Date(summary.scanner_last_heartbeat).toLocaleTimeString() : "N/A",
                    ok: true,
                  },
                  { label: "Latency", value: workerHealth?.latency_ms ? `${workerHealth.latency_ms.toFixed(0)}ms` : "N/A", ok: true },
                  { label: "API", value: health ? "CONNECTED" : "N/A", ok: !!health },
                ].map(({ label, value, ok }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-[#555]">{label}</span>
                    <span className={`font-mono text-[10px] ${ok ? "text-[#22c55e]" : "text-[#ef4444]"}`}>{value}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4">
              <div className="text-[10px] font-mono text-[#555] tracking-widest mb-3">QUICK LINKS</div>
              <div className="space-y-2 mb-4">
                <div className="font-mono text-[10px] text-[#666]">
                  Telegram, relatórios e comandos operacionais ficam no bot — use /status, /relatorio, /oportunidades no grupo.
                </div>
              </div>
              <div className="flex gap-2 pt-2 border-t border-[#1e1e1e]">
                <Btn variant="ghost" size="xs" onClick={() => onNavigate("system-health")}>SYSTEM HEALTH</Btn>
              </div>
            </Card>
          </div>

          {/* Top Opportunities — dados reais do /opportunities */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono text-[11px] text-[#C9A84C] tracking-widest">TOP OPPORTUNITIES</span>
              <Btn variant="gold" size="xs" onClick={() => onNavigate("opportunities")}>VIEW ALL →</Btn>
            </div>

            {loadingOpps && <LoadingState label="Carregando oportunidades..." />}
            {errorOpps && <ErrorState message={errorOpps} onRetry={reloadOpps} />}
            {!loadingOpps && !errorOpps && topOpps.length === 0 && (
              <EmptyState
                title="NO CONFIRMED OPPORTUNITIES"
                subtitle="The system is scanning the market. Setups will appear here as soon as they're detected — nothing is invented while the scanner works."
              />
            )}
            {!loadingOpps && !errorOpps && topOpps.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                {topOpps.map((o) => (
                  <OpportunityCard key={o.id} opp={o} onView={() => onNavigate("opportunities")} />
                ))}
              </div>
            )}
          </div>

          {/* Quick access row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Live Scanner", sub: scannerOnline ? "scanner online" : "verificar status", page: "scanner" as Page, tag: scannerOnline ? "ACTIVE" : "" },
              { label: "Playbooks", sub: "estratégias do sistema", page: "playbooks" as Page, tag: "" },
              { label: "Setups", sub: `${summary?.future_formation ?? "…"} em formação`, page: "setups" as Page, tag: "" },
              { label: "Performance", sub: "estatísticas reais", page: "performance" as Page, tag: "" },
            ].map(({ label, sub, page, tag }) => (
              <button
                key={label}
                onClick={() => onNavigate(page)}
                className="bg-[#111] border border-[#1e1e1e] rounded-sm p-4 text-left hover:border-[#2e2e2e] transition-colors group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] font-medium text-[#f0f0f0]">{label}</span>
                  {tag && <Badge variant={tag === "ACTIVE" ? "green" : "neutral"}>{tag}</Badge>}
                </div>
                <div className="text-[10px] text-[#555]">{sub}</div>
              </button>
            ))}
          </div>
        </>
      )}

      {loadingSummary && !summary && <LoadingState />}
    </div>
  );
}

function OpportunityCard({ opp, onView }: { opp: Opportunity; onView: () => void }) {
  const isGold = opp.score >= 85 && opp.status === "CONFIRMED";
  const fmt = (v: number | null) => (v === null ? "N/A" : v.toLocaleString(undefined, { maximumFractionDigits: 6 }));
  return (
    <Card
      className={`p-4 cursor-pointer hover:border-[#2e2e2e] transition-colors ${isGold ? "gold-glow border-[#C9A84C]/15" : ""}`}
      onClick={onView}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-mono text-[13px] font-600 text-[#f0f0f0]">{opp.asset}</div>
          <div className="mt-1">
            <DirectionBadge direction={opp.direction} />
          </div>
        </div>
        <div className="text-right">
          <ScoreBadge score={opp.score} />
          {isGold && <div className="font-mono text-[8px] text-[#C9A84C] tracking-widest mt-0.5">HIGH SCORE</div>}
        </div>
      </div>

      <div className="text-[9px] font-mono text-[#555] mb-2">
        {opp.timeframe} · {opp.playbook}
      </div>

      <div className="space-y-1 mb-3">
        <Row label="ENTRY" value={fmt(opp.entry)} />
        <Row label="STOP" value={fmt(opp.stop)} />
        <Row label="RR" value={opp.rr ? `1:${opp.rr.toFixed(1)}` : "N/A"} />
      </div>

      <div className="flex items-center justify-between">
        <StatusBadge status={opp.status} />
        <span className="font-mono text-[9px] text-[#444]">VIEW →</span>
      </div>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="font-mono text-[9px] text-[#444]">{label}</span>
      <span className="font-mono text-[10px] text-[#888] tabular-nums">{value}</span>
    </div>
  );
}
