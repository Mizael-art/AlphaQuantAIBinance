import Link from "next/link";
import { listOpportunities } from "@/lib/api";
import { StatusBadge, DecisionBadge, DirectionBadge, ScoreBar, ConfidenceLabel } from "@/components/badges";

export const dynamic = "force-dynamic";

export default async function ScannerPage({
  searchParams,
}: {
  searchParams: { status?: string; playbook?: string; asset?: string };
}) {
  let data;
  let error: string | null = null;
  try {
    data = await listOpportunities(searchParams);
  } catch (e) {
    error = e instanceof Error ? e.message : "Falha ao carregar oportunidades";
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink-100">Live Scanner</h1>
        <p className="text-sm text-ink-500">Ordenado por atualização mais recente</p>
      </div>

      {error && (
        <div className="rounded border border-state-bearish/40 bg-state-bearish/10 p-4 text-sm text-state-bearish">
          {error}
        </div>
      )}

      {data && data.opportunities.length === 0 && (
        <div className="rounded border border-base-700 bg-base-900 p-6 text-sm text-ink-500">
          NO HIGH-QUALITY OPPORTUNITY no momento — isso é um resultado operacional válido (seção 69).
        </div>
      )}

      {data && data.opportunities.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-base-700">
          <table className="w-full text-sm">
            <thead className="bg-base-900 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3">Asset</th>
                <th className="px-4 py-3">TF</th>
                <th className="px-4 py-3">Playbook</th>
                <th className="px-4 py-3">Direção</th>
                <th className="px-4 py-3">Score</th>
                <th className="px-4 py-3">Confiança</th>
                <th className="px-4 py-3">RR</th>
                <th className="px-4 py-3">Progresso</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Decisão</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-base-700 bg-base-950">
              {data.opportunities.map((o) => (
                <tr key={o.id} className="transition-colors hover:bg-base-900">
                  <td className="px-4 py-3">
                    <Link href={`/opportunities/${o.id}`} className="font-medium text-ink-100 hover:text-accent-teal">
                      {o.asset}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-ink-300">{o.timeframe}</td>
                  <td className="px-4 py-3 text-ink-300">{o.playbook}</td>
                  <td className="px-4 py-3">
                    <DirectionBadge direction={o.direction} />
                  </td>
                  <td className="px-4 py-3">
                    <ScoreBar score={o.score} />
                  </td>
                  <td className="px-4 py-3">
                    <ConfidenceLabel confidence={o.confidence} />
                  </td>
                  <td className="px-4 py-3 tabular-nums text-ink-300">
                    {o.rr !== null ? `1:${o.rr.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-ink-300">{o.progress.toFixed(0)}%</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="px-4 py-3">
                    <DecisionBadge decision={o.decision} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
