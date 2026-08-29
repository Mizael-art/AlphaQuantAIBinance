import { useState } from "react";
import { Card, FilterChips, StatusBadge, DirectionBadge, ScoreBadge, Btn, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api, Opportunity } from "../lib/api";
import { useApi } from "../lib/useApi";

const REFRESH_MS = 20_000;

const STATUS_FILTERS = ["ALL", "CONFIRMED", "FORMATION", "INVALIDATED"];
const DIR_FILTERS = ["ALL", "LONG", "SHORT"];
const SCORE_FILTERS = ["ALL", ">80", ">70", ">60"];

export default function Scanner() {
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [dirFilter, setDirFilter] = useState("ALL");
  const [scoreFilter, setScoreFilter] = useState("ALL");
  const [sort, setSort] = useState<"score" | "asset">("score");

  const { data, loading, error, reload } = useApi(() => api.opportunities({ limit: 200 }), [], REFRESH_MS);
  const all = data?.opportunities || [];

  let assets = [...all];
  if (statusFilter !== "ALL") assets = assets.filter((a) => a.status === statusFilter);
  if (dirFilter !== "ALL") assets = assets.filter((a) => a.direction === dirFilter);
  if (scoreFilter === ">80") assets = assets.filter((a) => a.score > 80);
  if (scoreFilter === ">70") assets = assets.filter((a) => a.score > 70);
  if (scoreFilter === ">60") assets = assets.filter((a) => a.score > 60);
  if (sort === "score") assets.sort((a, b) => b.score - a.score);
  if (sort === "asset") assets.sort((a, b) => a.asset.localeCompare(b.asset));

  const confirmed = all.filter((a) => a.status === "CONFIRMED").length;
  const formation = all.filter((a) => a.status === "FORMATION").length;

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0] tracking-wide">Live Scanner</h1>
          <p className="text-[11px] text-[#555]">Real-time analysis across all monitored pairs.</p>
        </div>
        <div className="hidden md:flex items-center gap-4 text-right">
          <Stat v={String(all.length)} l="OPPORTUNITIES" />
          <Stat v={String(formation)} l="FORMING" />
          <Stat v={String(confirmed)} l="CONFIRMED" highlight />
        </div>
      </div>

      <div className="space-y-3 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <FilterChips options={STATUS_FILTERS} active={statusFilter} onSelect={setStatusFilter} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <FilterChips options={DIR_FILTERS} active={dirFilter} onSelect={setDirFilter} />
          <FilterChips options={SCORE_FILTERS} active={scoreFilter} onSelect={setScoreFilter} />
          <div className="ml-auto flex items-center gap-2">
            <span className="font-mono text-[9px] text-[#444]">SORT</span>
            <Btn variant={sort === "score" ? "gold" : "ghost"} size="xs" onClick={() => setSort("score")}>SCORE</Btn>
            <Btn variant={sort === "asset" ? "gold" : "ghost"} size="xs" onClick={() => setSort("asset")}>ASSET</Btn>
          </div>
        </div>
      </div>

      {loading && !data && <LoadingState label="Escaneando o mercado..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && assets.length === 0 && (
        <EmptyState title="NO OPPORTUNITIES" subtitle="Nenhuma oportunidade encontrada para os filtros atuais." />
      )}

      {assets.length > 0 && (
        <>
          <div className="flex items-center gap-4 mb-3">
            <span className="font-mono text-[10px] text-[#555]">{assets.length} shown</span>
            <span className="font-mono text-[10px] text-[#C9A84C]">{confirmed} confirmed</span>
            <span className="font-mono text-[10px] text-[#555]">{formation} forming</span>
          </div>

          <Card className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr className="border-b border-[#1e1e1e]">
                  {["ASSET", "TF", "PLAYBOOK", "DIR", "SCORE", "CONFIDENCE", "RR", "PROGRESS", "STATUS", "DECISION"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-mono text-[9px] text-[#444] tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {assets.map((a: Opportunity, i) => (
                  <tr key={a.id} className={`border-b border-[#111] hover:bg-[#151515] transition-colors ${i % 2 === 0 ? "" : "bg-[#0d0d0d]"}`}>
                    <td className="px-3 py-2.5"><span className="font-mono text-[11px] font-600 text-[#f0f0f0]">{a.asset}</span></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[10px] text-[#666]">{a.timeframe}</span></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[9px] text-[#555]">{a.playbook}</span></td>
                    <td className="px-3 py-2.5"><DirectionBadge direction={a.direction} /></td>
                    <td className="px-3 py-2.5"><ScoreBadge score={a.score} /></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[9px] text-[#666]">{a.confidence}</span></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[10px] text-[#888] tabular-nums">{a.rr ? `1:${a.rr.toFixed(1)}` : "N/A"}</span></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[10px] text-[#888] tabular-nums">{a.progress.toFixed(0)}%</span></td>
                    <td className="px-3 py-2.5"><StatusBadge status={a.status} /></td>
                    <td className="px-3 py-2.5"><span className="font-mono text-[9px] text-[#666]">{a.decision ?? "—"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ v, l, highlight }: { v: string; l: string; highlight?: boolean }) {
  return (
    <div className="text-right">
      <div className={`font-mono text-[18px] font-600 tabular-nums ${highlight ? "text-[#C9A84C]" : "text-[#f0f0f0]"}`}>{v}</div>
      <div className="font-mono text-[9px] text-[#444] tracking-widest">{l}</div>
    </div>
  );
}
