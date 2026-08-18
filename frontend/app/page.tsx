import Link from "next/link";
import { getSummary } from "@/lib/api";
import { LiveDot } from "@/components/badges";

function Card({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-base-700 bg-base-900 p-5">
      <div className="text-xs uppercase tracking-wide text-ink-500">{label}</div>
      <div className={`mt-2 text-3xl font-semibold tabular-nums ${accent ? "text-accent-teal" : "text-ink-100"}`}>
        {value}
      </div>
    </div>
  );
}

export default async function DashboardPage() {
  let summary;
  let error: string | null = null;
  try {
    summary = await getSummary();
  } catch (e) {
    error = e instanceof Error ? e.message : "Falha ao carregar resumo";
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-100">Market Intelligence</h1>
          <p className="text-sm text-ink-500">Últimas 24 horas</p>
        </div>
        {summary && <LiveDot online={summary.scanner_status === "ONLINE"} />}
      </div>

      {error && (
        <div className="rounded border border-state-bearish/40 bg-state-bearish/10 p-4 text-sm text-state-bearish">
          {error}. Confirme que a API está rodando e <code>NEXT_PUBLIC_API_BASE_URL</code> está configurada.
        </div>
      )}

      {summary && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Card label="Oportunidades analisadas" value={summary.opportunities_analyzed} />
            <Card label="Score ≥ 70" value={summary.score_ge_70} />
            <Card label="Score ≥ 80" value={summary.score_ge_80} accent />
            <Card label="Score ≥ 90" value={summary.score_ge_90} accent />
            <Card label="Confirmadas (ENTRAR)" value={summary.confirmed} />
            <Card label="Em formação (Future)" value={summary.future_formation} />
            <Card label="Reprovadas" value={summary.invalidated} />
            <Card label="Scanner" value={summary.scanner_status} accent={summary.scanner_status === "ONLINE"} />
          </div>

          <div className="mt-8 flex gap-3">
            <Link
              href="/scanner"
              className="rounded border border-accent-teal/40 bg-accent-teal/10 px-4 py-2 text-sm font-medium text-accent-teal hover:bg-accent-teal/20"
            >
              Ver Live Scanner →
            </Link>
            <Link
              href="/playbooks"
              className="rounded border border-base-700 bg-base-900 px-4 py-2 text-sm font-medium text-ink-300 hover:bg-base-800"
            >
              Ver Playbooks
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
