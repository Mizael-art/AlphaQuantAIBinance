import { listPlaybooks } from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: "text-state-bullish",
  VALIDATING: "text-state-warn",
  EXPERIMENTAL: "text-accent-cyan",
  SUSPENDED: "text-ink-500",
  RETIRED: "text-ink-500",
};

export default async function PlaybooksPage() {
  let data;
  let error: string | null = null;
  try {
    data = await listPlaybooks();
  } catch (e) {
    error = e instanceof Error ? e.message : "Falha ao carregar playbooks";
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink-100">Playbooks</h1>
        <p className="text-sm text-ink-500">
          Nenhum playbook fica ACTIVE sem passar por backtest + forward test (seção 55).
        </p>
      </div>

      {error && (
        <div className="rounded border border-state-bearish/40 bg-state-bearish/10 p-4 text-sm text-state-bearish">
          {error}
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {data.playbooks.map((p) => (
            <div key={p.id} className="rounded-lg border border-base-700 bg-base-900 p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-medium text-ink-100">{p.name}</h2>
                <span className={`text-xs font-semibold uppercase ${STATUS_COLOR[p.status] ?? "text-ink-500"}`}>
                  {p.status}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-ink-500">
                <div>
                  Versão
                  <div className="text-ink-300">{p.version}</div>
                </div>
                <div>
                  Score mín.
                  <div className="text-ink-300">{p.minimum_score.toFixed(0)}</div>
                </div>
                <div>
                  RR mín.
                  <div className="text-ink-300">{p.minimum_rr.toFixed(1)}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
