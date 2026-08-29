import { useState } from "react";
import { Card, FilterChips, StatusBadge, DirectionBadge, ScoreBadge, ProgressBar, LoadingState, ErrorState, EmptyState } from "../components/ui";
import { api, Opportunity } from "../lib/api";
import { useApi } from "../lib/useApi";

const TABS = ["ALL", "CONFIRMED", "FORMATION", "INVALIDATED"];
const REFRESH_MS = 20_000;

export default function Setups() {
  const [tab, setTab] = useState("ALL");
  const { data, loading, error, reload } = useApi(() => api.opportunities({ limit: 200 }), [], REFRESH_MS);
  const all = data?.opportunities || [];

  const filtered = tab === "ALL" ? all : all.filter((s) => s.status === tab);

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Setups</h1>
          <p className="text-[11px] text-[#555]">Setup pipeline — formation progress and status.</p>
        </div>
        <div className="flex gap-4">
          {[
            { l: "CONFIRMED", v: all.filter((s) => s.status === "CONFIRMED").length, c: "text-[#C9A84C]" },
            { l: "FORMATION", v: all.filter((s) => s.status === "FORMATION").length, c: "text-[#60a5fa]" },
          ].map(({ l, v, c }) => (
            <div key={l} className="text-right">
              <div className={`font-mono text-[16px] font-600 ${c}`}>{v}</div>
              <div className="font-mono text-[8px] text-[#444] tracking-widest">{l}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-5">
        <FilterChips options={TABS} active={tab} onSelect={setTab} />
      </div>

      {loading && !data && <LoadingState label="Carregando setups..." />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState title="NO SETUPS" subtitle="Nenhum setup para esse filtro no momento." />
      )}

      {filtered.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((s) => (
            <SetupCard key={s.id} setup={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function SetupCard({ setup }: { setup: Opportunity }) {
  const isConfirmed = setup.status === "CONFIRMED";
  const pColor = setup.progress === 100 ? "#22c55e" : setup.progress >= 60 ? "#C9A84C" : "#555";
  return (
    <Card className={`p-4 hover:border-[#2e2e2e] transition-colors ${isConfirmed ? "gold-glow border-[#C9A84C]/15" : ""}`}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-mono text-[13px] font-600 text-[#f0f0f0]">{setup.asset}</div>
          <div className="font-mono text-[9px] text-[#444] mt-0.5">{setup.playbook} · {setup.timeframe}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <ScoreBadge score={setup.score} />
          <StatusBadge status={setup.status} />
        </div>
      </div>

      <div className="mb-3">
        <DirectionBadge direction={setup.direction} />
      </div>

      <div className="mb-1">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] text-[#444]">PROGRESS</span>
          <span className="font-mono text-[10px] tabular-nums" style={{ color: pColor }}>{setup.progress.toFixed(0)}%</span>
        </div>
        <ProgressBar value={setup.progress} color={pColor} />
      </div>
    </Card>
  );
}
