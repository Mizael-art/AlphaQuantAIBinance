const STATUS_STYLES: Record<string, string> = {
  CONFIRMED: "bg-state-bullish/15 text-state-bullish border-state-bullish/30",
  FORMATION: "bg-state-warn/15 text-state-warn border-state-warn/30",
  INVALIDATED: "bg-base-700 text-ink-500 border-base-600",
  EXPIRED: "bg-base-700 text-ink-500 border-base-600",
};

const DECISION_STYLES: Record<string, string> = {
  ENTRAR: "bg-state-bullish/15 text-state-bullish border-state-bullish/30",
  ESPERAR: "bg-state-warn/15 text-state-warn border-state-warn/30",
  REPROVAR: "bg-state-bearish/15 text-state-bearish border-state-bearish/30",
};

function Badge({ label, className }: { label: string; className: string }) {
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge label={status} className={STATUS_STYLES[status] ?? "bg-base-700 text-ink-300 border-base-600"} />;
}

export function DecisionBadge({ decision }: { decision: string | null }) {
  if (!decision) return <Badge label="—" className="bg-base-700 text-ink-500 border-base-600" />;
  return (
    <Badge label={decision} className={DECISION_STYLES[decision] ?? "bg-base-700 text-ink-300 border-base-600"} />
  );
}

export function DirectionBadge({ direction }: { direction: string }) {
  const isLong = direction === "LONG";
  return (
    <Badge
      label={direction}
      className={
        isLong
          ? "bg-state-bullish/15 text-state-bullish border-state-bullish/30"
          : "bg-state-bearish/15 text-state-bearish border-state-bearish/30"
      }
    />
  );
}

export function ConfidenceLabel({ confidence }: { confidence: string }) {
  const color =
    confidence === "ALTA" ? "text-accent-teal" : confidence === "MODERADA" ? "text-state-warn" : "text-ink-500";
  return <span className={`text-sm font-medium ${color}`}>{confidence}</span>;
}

export function ScoreBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-accent-teal" : score >= 70 ? "bg-state-warn" : "bg-ink-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-base-700">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
      </div>
      <span className="text-sm tabular-nums text-ink-100">{score.toFixed(0)}</span>
    </div>
  );
}

export function LiveDot({ online }: { online: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      <span
        className={`live-dot h-2 w-2 rounded-full ${online ? "bg-state-bullish" : "bg-state-bearish"}`}
      />
      {online ? "LIVE" : "OFFLINE"}
    </span>
  );
}
