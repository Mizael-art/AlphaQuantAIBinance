import { notFound } from "next/navigation";
import { getOpportunity } from "@/lib/api";
import { StatusBadge, DecisionBadge, DirectionBadge, ConfidenceLabel } from "@/components/badges";

export const dynamic = "force-dynamic";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-1 text-sm tabular-nums text-ink-100">{value}</div>
    </div>
  );
}

export default async function OpportunityDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  if (Number.isNaN(id)) notFound();

  let opp;
  try {
    opp = await getOpportunity(id);
  } catch {
    notFound();
  }
  if (!opp) notFound();

  const snapshot = opp.audit_snapshot as {
    conditions_met?: string[];
    conditions_missing?: string[];
    targets?: { price: number; source: string }[];
    regime?: string;
    htf_regime?: string | null;
    quality_filter?: { approved: boolean; reasons: string[] } | null;
    decision?: { decision: string; reasons: string[] } | null;
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-xl font-semibold text-ink-100">
          {opp.asset} · {opp.timeframe}
        </h1>
        <DirectionBadge direction={opp.direction} />
        <StatusBadge status={opp.status} />
        <DecisionBadge decision={opp.decision} />
      </div>
      <p className="mb-6 text-sm text-ink-500">{opp.playbook}</p>

      <div className="grid grid-cols-2 gap-4 rounded-lg border border-base-700 bg-base-900 p-5 md:grid-cols-4">
        <Field label="Score" value={`${opp.score.toFixed(0)}/100`} />
        <Field label="Confiança" value={opp.confidence} />
        <Field label="Progresso" value={`${opp.progress.toFixed(0)}%`} />
        <Field label="RR" value={opp.rr !== null ? `1:${opp.rr.toFixed(2)}` : "—"} />
        <Field label="Entrada" value={opp.entry !== null ? opp.entry.toFixed(4) : "—"} />
        <Field label="Stop" value={opp.stop !== null ? opp.stop.toFixed(4) : "—"} />
        <Field label="TP1" value={opp.tp1 !== null ? opp.tp1.toFixed(4) : "—"} />
        <Field label="TP2" value={opp.tp2 !== null ? opp.tp2.toFixed(4) : "—"} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-base-700 bg-base-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-state-bullish">Evidências favoráveis</h2>
          <ul className="space-y-1.5 text-sm text-ink-300">
            {(snapshot.conditions_met ?? []).map((c, i) => (
              <li key={i}>✓ {c}</li>
            ))}
            {(snapshot.conditions_met ?? []).length === 0 && <li className="text-ink-500">—</li>}
          </ul>
        </div>
        <div className="rounded-lg border border-base-700 bg-base-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-state-bearish">Dados ausentes / condições faltantes</h2>
          <ul className="space-y-1.5 text-sm text-ink-300">
            {(snapshot.conditions_missing ?? []).map((c, i) => (
              <li key={i}>✗ {c}</li>
            ))}
            {(snapshot.conditions_missing ?? []).length === 0 && <li className="text-ink-500">—</li>}
          </ul>
        </div>
      </div>

      {snapshot.quality_filter && (
        <div className="mt-4 rounded-lg border border-base-700 bg-base-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-ink-100">Quality Filter</h2>
          <p className={snapshot.quality_filter.approved ? "text-state-bullish" : "text-state-bearish"}>
            {snapshot.quality_filter.approved ? "APROVADO" : "REPROVADO"}
          </p>
          <ul className="mt-2 space-y-1 text-sm text-ink-300">
            {snapshot.quality_filter.reasons.map((r, i) => (
              <li key={i}>• {r}</li>
            ))}
          </ul>
        </div>
      )}

      {snapshot.decision && (
        <div className="mt-4 rounded-lg border border-base-700 bg-base-900 p-5">
          <h2 className="mb-3 text-sm font-semibold text-ink-100">Decision Engine</h2>
          <p className="text-ink-100">{snapshot.decision.decision}</p>
          <ul className="mt-2 space-y-1 text-sm text-ink-300">
            {snapshot.decision.reasons.map((r, i) => (
              <li key={i}>• {r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 rounded-lg border border-base-700 bg-base-900 p-5">
        <h2 className="mb-3 text-sm font-semibold text-ink-100">Evidence (auditoria completa)</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="py-1.5 pr-4">Categoria</th>
              <th className="py-1.5 pr-4">Critério</th>
              <th className="py-1.5">Pontos</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-800">
            {opp.evidence.map((e, i) => (
              <tr key={i}>
                <td className="py-1.5 pr-4 text-ink-500">{e.category}</td>
                <td className="py-1.5 pr-4 text-ink-300">{e.evidence}</td>
                <td className="py-1.5 tabular-nums text-ink-100">{e.score.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-6 text-xs text-ink-500">
        ⚠️ Não é garantia de resultado. Gestão de risco é obrigatória. ALPHAQUANT X.
      </p>
    </div>
  );
}
