import { useState } from "react";
import {
  Card, FilterChips, StatusBadge, DirectionBadge, ScoreBadge,
  ConfluenceBar, Btn, LoadingState, ErrorState, EmptyState,
} from "../components/ui";
import { api, Opportunity } from "../lib/api";
import { useApi } from "../lib/useApi";

const FILTERS = ["ALL", "CONFIRMED", "FORMATION", "INVALIDATED"];
const REFRESH_MS = 20_000;

interface Group {
  key: string;
  asset: string;
  timeframe: string;
  direction: "LONG" | "SHORT";
  best: Opportunity; // maior score do grupo — usado como "cara" do card
  confirmed: Opportunity[]; // playbooks que bateram ENTRAR — a confluência real
  all: Opportunity[];
  status: string;
}

function groupByAssetTimeframe(opps: Opportunity[]): Group[] {
  const map = new Map<string, Opportunity[]>();
  for (const o of (opps || [])) {
    if (!o) continue;
    const key = `${o.asset || "UNKNOWN"}__${o.timeframe || "1H"}__${o.direction || "LONG"}`;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(o);
  }
  return Array.from(map.entries())
    .map(([key, group]) => {
      const confirmed = group.filter((o) => o.status === "CONFIRMED");
      const best = [...group].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || group[0];
      const status = confirmed.length > 0 ? "CONFIRMED" : (best?.status || "FORMATION");
      return {
        key,
        asset: best?.asset || "UNKNOWN",
        timeframe: best?.timeframe || "1H",
        direction: (best?.direction || "LONG") as "LONG" | "SHORT",
        best,
        confirmed,
        all: group,
        status,
      };
    })
    .filter((g) => g.best);
}

export default function Opportunities() {
  const [filter, setFilter] = useState("ALL");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const { data, loading, error, reload } = useApi(() => api.opportunities({ limit: 200 }), [], REFRESH_MS);
  const all = data?.opportunities || [];
  const groups = groupByAssetTimeframe(all.filter((o) => o.status !== "INVALIDATED" || filter === "INVALIDATED" || filter === "ALL"));

  const filtered = filter === "ALL" ? groups : groups.filter((g) => g.status === filter);
  const sel = selectedKey ? groups.find((g) => g.key === selectedKey) : null;
  const confirmedCount = groups.filter((g) => g.status === "CONFIRMED").length;

  if (sel) return <OpportunityDetail group={sel} onBack={() => setSelectedKey(null)} />;

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Opportunities</h1>
          <p className="text-[11px] text-[#555]">Detected setups with strategy confluence analysis.</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-[#C9A84C]">{confirmedCount} CONFIRMED</span>
        </div>
      </div>

      <div className="mb-4">
        <FilterChips options={FILTERS} active={filter} onSelect={setFilter} />
      </div>

      {loading && !data && <LoadingState label="Carregando oportunidades..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState title="NO OPPORTUNITIES" subtitle="Nenhuma oportunidade para esse filtro no momento." />
      )}

      {filtered.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((g) => (
            <OppCard key={g.key} group={g} onClick={() => setSelectedKey(g.key)} />
          ))}
        </div>
      )}
    </div>
  );
}

function confluenceLabel(n: number): string {
  if (n >= 4) return "VERY HIGH";
  if (n === 3) return "HIGH";
  if (n === 2) return "MEDIUM";
  return "LOW";
}

function OppCard({ group, onClick }: { group: Group; onClick: () => void }) {
  const isGold = group.status === "CONFIRMED" && group.best.score >= 80;
  return (
    <Card
      className={`p-4 cursor-pointer hover:border-[#2e2e2e] transition-all ${isGold ? "gold-glow border-[#C9A84C]/15" : ""}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-mono text-[14px] font-700 text-[#f0f0f0]">{group.asset}</div>
          <div className="text-[10px] text-[#555] mb-2">{group.timeframe}</div>
          <DirectionBadge direction={group.direction} />
        </div>
        <div className="text-right">
          <ScoreBadge score={group.best.score} />
          {group.confirmed.length > 1 && (
            <div className="font-mono text-[8px] tracking-widest mt-1 text-[#C9A84C]">
              {confluenceLabel(group.confirmed.length)} CONFLUENCE
            </div>
          )}
        </div>
      </div>

      <div className="mb-3 space-y-1">
        {(group.confirmed.length > 0 ? group.confirmed : [group.best]).map((o) => (
          <div key={o.id} className="flex items-center gap-1.5">
            <span className={o.status === "CONFIRMED" ? "text-[#22c55e] text-[9px]" : "text-[#666] text-[9px]"}>
              {o.status === "CONFIRMED" ? "✓" : "·"}
            </span>
            <span className="font-mono text-[9px] text-[#555]">{o.playbook}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 mb-3 pt-3 border-t border-[#1a1a1a]">
        <div>
          <div className="font-mono text-[8px] text-[#444]">ENTRY</div>
          <div className="font-mono text-[9px] text-[#888] tabular-nums">{group.best.entry ?? "N/A"}</div>
        </div>
        <div>
          <div className="font-mono text-[8px] text-[#444]">STOP</div>
          <div className="font-mono text-[9px] text-[#ef4444] tabular-nums">{group.best.stop ?? "N/A"}</div>
        </div>
        <div>
          <div className="font-mono text-[8px] text-[#444]">RR</div>
          <div className="font-mono text-[9px] text-[#C9A84C] tabular-nums">{group.best.rr ? `1:${group.best.rr.toFixed(1)}` : "N/A"}</div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <StatusBadge status={group.status} />
        <span className="font-mono text-[9px] text-[#333]">ANALYSIS →</span>
      </div>
    </Card>
  );
}

function OpportunityDetail({ group, onBack }: { group: Group; onBack: () => void }) {
  const opp = group.best;
  const { data: detail } = useApi(() => api.opportunityDetail(opp.id), [opp.id]);
  const reasons: string[] =
    detail?.audit_snapshot?.decision_engine?.reasons || detail?.audit_snapshot?.quality_filter?.reasons || [];

  return (
    <div className="p-5 lg:p-6 max-w-[900px]">
      <button onClick={onBack} className="flex items-center gap-2 font-mono text-[10px] text-[#555] hover:text-[#888] mb-5 transition-colors">
        ← BACK TO OPPORTUNITIES
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="font-mono text-[22px] font-700 text-[#f0f0f0]">{group.asset}</h1>
            <DirectionBadge direction={group.direction} />
          </div>
          <div className="text-[11px] text-[#555]">{group.timeframe}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[28px] font-700 text-[#C9A84C] tabular-nums">{opp.score.toFixed(0)}</div>
          <div className="font-mono text-[9px] text-[#555]">SCORE</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card className="p-4 gold-glow border-[#C9A84C]/15">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-mono text-[10px] text-[#C9A84C] tracking-widest">CONFLUENCE ENGINE</div>
                <div className="font-mono text-[13px] font-600 text-[#f0f0f0] mt-1">
                  {group.confirmed.length > 0
                    ? `${group.confirmed.length} STRATEG${group.confirmed.length > 1 ? "IES" : "Y"} CONFIRMING`
                    : "AGUARDANDO CONFIRMAÇÃO"}
                </div>
              </div>
              <StatusBadge status={group.status} />
            </div>
            <div className="space-y-2">
              {group.all.map((o) => (
                <div key={o.id} className="flex items-center gap-2 bg-[#0d0d0d] px-3 py-2 rounded-sm">
                  <span className={o.status === "CONFIRMED" ? "text-[#22c55e] text-[10px]" : "text-[#666] text-[10px]"}>
                    {o.status === "CONFIRMED" ? "✓" : "·"}
                  </span>
                  <span className="font-mono text-[10px] text-[#888]">{o.playbook}</span>
                  <span className="font-mono text-[9px] text-[#444] ml-auto">score {o.score.toFixed(0)}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t border-[#1e1e1e]">
              <ConfluenceBar score={opp.score} />
            </div>
          </Card>

          <Card className="p-4">
            <div className="font-mono text-[10px] text-[#555] tracking-widest mb-3">WHY?</div>
            {reasons.length > 0 ? (
              <div className="space-y-2">
                {reasons.map((r, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-[#22c55e] text-[10px] mt-0.5">✓</span>
                    <span className="text-[11px] text-[#888]">{r}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="font-mono text-[10px] text-[#444]">
                Motivos detalhados não disponíveis para essa oportunidade específica.
              </span>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <div className="font-mono text-[10px] text-[#555] tracking-widest mb-3">LEVELS</div>
            <div className="space-y-2">
              <Row label="ENTRY" value={String(opp.entry ?? "N/A")} color="text-[#f0f0f0]" />
              <Row label="STOP" value={String(opp.stop ?? "N/A")} color="text-[#ef4444]" />
              <div className="pt-1 border-t border-[#1a1a1a] mt-1" />
              <Row label="TP1" value={String(opp.tp1 ?? "N/A")} color="text-[#22c55e]" />
              <Row label="TP2" value={String(opp.tp2 ?? "N/A")} color="text-[#22c55e]" />
              <Row label="TP3" value={String(opp.tp3 ?? "N/A")} color="text-[#22c55e]" />
              <div className="pt-1 border-t border-[#1a1a1a] mt-1" />
              <Row label="RR" value={opp.rr ? `1:${opp.rr.toFixed(1)}` : "N/A"} color="text-[#C9A84C]" />
            </div>
          </Card>

          <Card className={`p-4 ${group.status === "CONFIRMED" ? "gold-glow border-[#C9A84C]/20" : ""}`}>
            <div className="font-mono text-[10px] text-[#555] tracking-widest mb-2">DECISION</div>
            <StatusBadge status={group.status} />
          </Card>

          <div className="flex flex-col gap-2">
            <Btn variant="ghost" size="sm" disabled title="Gráfico ainda não integrado (fase futura — Trading Terminal)">VIEW CHART</Btn>
          </div>
        </div>
      </div>
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
