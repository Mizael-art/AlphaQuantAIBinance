import { Card, LoadingState, ErrorState } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";

const REFRESH_MS = 15_000;

// Serviços com heartbeat real hoje: só "worker" grava em SystemHealth
// (emit_heartbeat, worker/app/main.py). API é inferida ONLINE pelo
// próprio fetch ter respondido. Database/Telegram/Market Data ainda
// não têm um health check dedicado escrevendo status — mostrar
// "NOT MONITORED" em vez de inventar ONLINE/OFFLINE pra eles.
const KNOWN_SERVICES = ["worker"];

export default function SystemHealth() {
  const { data: health, loading, error, reload } = useApi(() => api.health(), [], REFRESH_MS);

  const workerRow = health?.services?.["worker"];
  const apiOnline = !!health;
  const overallHealth = !health ? "UNKNOWN" : apiOnline && workerRow?.status === "ONLINE" ? "ONLINE" : "WARNING";

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">System Health</h1>
          <p className="text-[11px] text-[#555]">Live service status.</p>
        </div>
        <div className="text-right">
          <div className={`font-mono text-[11px] tracking-wider ${overallHealth === "ONLINE" ? "text-[#22c55e]" : overallHealth === "WARNING" ? "text-[#f59e0b]" : "text-[#ef4444]"}`}>
            ● SYSTEM {overallHealth}
          </div>
          {health && <div className="font-mono text-[9px] text-[#444] mt-0.5">{new Date(health.checked_at).toLocaleTimeString()}</div>}
        </div>
      </div>

      {loading && !health && <LoadingState label="Verificando status dos serviços..." />}
      {error && <ErrorState message={error} onRetry={reload} />}

      {health && (
        <>
          {/* Services */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
            <ServiceCard
              name="API"
              status="ONLINE"
              latency={null}
              lastHeartbeat={health.checked_at}
            />
            {KNOWN_SERVICES.map((key) => {
              const row = health.services[key];
              return (
                <ServiceCard
                  key={key}
                  name={key.charAt(0).toUpperCase() + key.slice(1)}
                  status={row?.status ?? "UNKNOWN"}
                  latency={row?.latency_ms ?? null}
                  lastHeartbeat={row?.last_heartbeat ?? null}
                />
              );
            })}
            {["database", "telegram", "market-data"].map((name) => (
              <ServiceCard key={name} name={name} status="NOT MONITORED" latency={null} lastHeartbeat={null} />
            ))}
          </div>

          {/* Scanner status — a partir da linha "worker" do /health */}
          <Card className="p-4 mb-5">
            <div className="font-mono text-[9px] text-[#C9A84C] tracking-widest mb-3">SCANNER / WORKER</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { l: "STATUS", v: workerRow?.status ?? "N/A" },
                { l: "LAST HEARTBEAT", v: workerRow?.last_heartbeat ? new Date(workerRow.last_heartbeat).toLocaleTimeString() : "N/A" },
                { l: "LATENCY", v: workerRow?.latency_ms ? `${workerRow.latency_ms.toFixed(0)}ms` : "N/A" },
              ].map(({ l, v }) => (
                <div key={l}>
                  <div className="font-mono text-[8px] text-[#444] tracking-widest mb-0.5">{l}</div>
                  <div className="font-mono text-[12px] text-[#888]">{v}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* System logs — sem endpoint de logs na API ainda */}
          <Card>
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e1e]">
              <div className="font-mono text-[10px] text-[#555] tracking-widest">SYSTEM LOGS</div>
            </div>
            <div className="p-4 font-mono text-[10px] text-[#555]">
              Logs detalhados por ciclo (CYCLE STATS, OPPORTUNITY, erros) ficam nos logs do Render — ainda não há
              endpoint na API para trazê-los pra cá. Use /status no Telegram para um resumo rápido, ou o painel do Render
              para o log completo.
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function ServiceCard({
  name, status, latency, lastHeartbeat,
}: {
  name: string; status: string; latency: number | null; lastHeartbeat: string | null;
}) {
  const statusColor = status === "ONLINE" ? "#22c55e" : status === "DEGRADED" || status === "WARNING" ? "#f59e0b" : status === "NOT MONITORED" || status === "UNKNOWN" ? "#444" : "#ef4444";
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-[11px] font-600 text-[#f0f0f0]">{name}</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full pulse-dot" style={{ backgroundColor: statusColor }} />
          <span className="font-mono text-[10px]" style={{ color: statusColor }}>{status}</span>
        </div>
      </div>
      <div className="space-y-1">
        <div className="flex justify-between">
          <span className="font-mono text-[9px] text-[#444]">Latency</span>
          <span className="font-mono text-[9px] text-[#666]">{latency ? `${latency.toFixed(0)}ms` : "N/A"}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-mono text-[9px] text-[#444]">Last heartbeat</span>
          <span className="font-mono text-[9px] text-[#666]">{lastHeartbeat ? new Date(lastHeartbeat).toLocaleTimeString() : "N/A"}</span>
        </div>
      </div>
    </Card>
  );
}
