import { getHealth } from "@/lib/api";
import { LiveDot } from "@/components/badges";

export const dynamic = "force-dynamic";

function statusColor(status: string) {
  if (status === "ONLINE") return "text-state-bullish";
  if (status === "DEGRADED") return "text-state-warn";
  return "text-state-bearish";
}

export default async function HealthPage() {
  let data;
  let error: string | null = null;
  try {
    data = await getHealth();
  } catch (e) {
    error = e instanceof Error ? e.message : "Falha ao carregar system health";
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink-100">System Health</h1>
      </div>

      {error && (
        <div className="rounded border border-state-bearish/40 bg-state-bearish/10 p-4 text-sm text-state-bearish">
          {error}
        </div>
      )}

      {data && (
        <div className="rounded-lg border border-base-700 bg-base-900 p-5">
          <div className="mb-4 flex items-center gap-2">
            <LiveDot online={data.status === "ok"} />
            <span className="text-xs text-ink-500">verificado em {new Date(data.checked_at).toLocaleString("pt-BR")}</span>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="py-1.5 pr-4">Serviço</th>
                <th className="py-1.5 pr-4">Status</th>
                <th className="py-1.5 pr-4">Último heartbeat</th>
                <th className="py-1.5">Latência (ms)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-base-800">
              {Object.entries(data.services).map(([service, info]) => (
                <tr key={service}>
                  <td className="py-1.5 pr-4 text-ink-100">{service}</td>
                  <td className={`py-1.5 pr-4 font-medium ${statusColor(info.status)}`}>{info.status}</td>
                  <td className="py-1.5 pr-4 text-ink-300">
                    {info.last_heartbeat ? new Date(info.last_heartbeat).toLocaleString("pt-BR") : "—"}
                  </td>
                  <td className="py-1.5 tabular-nums text-ink-300">
                    {info.latency_ms !== null ? info.latency_ms.toFixed(1) : "—"}
                  </td>
                </tr>
              ))}
              {Object.keys(data.services).length === 0 && (
                <tr>
                  <td colSpan={4} className="py-3 text-ink-500">
                    Nenhum serviço reportou heartbeat ainda.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
