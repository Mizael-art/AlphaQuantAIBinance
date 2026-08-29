import { ReactNode } from "react";

// ─── Badge ───────────────────────────────────────────────────────────────────

type BadgeVariant = "gold" | "green" | "red" | "neutral" | "blue" | "warn";

export function Badge({ variant = "neutral", children }: { variant?: BadgeVariant; children: ReactNode }) {
  const styles: Record<BadgeVariant, string> = {
    gold: "bg-[#C9A84C]/10 text-[#C9A84C] border border-[#C9A84C]/20",
    green: "bg-[#22c55e]/10 text-[#22c55e] border border-[#22c55e]/20",
    red: "bg-[#ef4444]/10 text-[#ef4444] border border-[#ef4444]/20",
    neutral: "bg-[#1c1c1c] text-[#888] border border-[#2e2e2e]",
    blue: "bg-[#3b82f6]/10 text-[#60a5fa] border border-[#3b82f6]/20",
    warn: "bg-[#f59e0b]/10 text-[#f59e0b] border border-[#f59e0b]/20",
  };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 font-mono text-[9px] tracking-widest rounded-sm ${styles[variant]}`}>
      {children}
    </span>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, BadgeVariant> = {
    CONFIRMED: "gold",
    ACTIVE: "green",
    ONLINE: "green",
    CONNECTED: "green",
    FORMATION: "blue",
    WATCH: "blue",
    "SETUP FORMING": "blue",
    "WAIT TRIGGER": "warn",
    "WAIT PULLBACK": "warn",
    WARNING: "warn",
    EXPERIMENTAL: "warn",
    INVALIDATED: "red",
    REJECTED: "red",
    OFFLINE: "red",
    DISCONNECTED: "red",
    VALIDATING: "neutral",
    DISABLED: "neutral",
    COMPLETED: "neutral",
    ENTER: "gold",
  };
  const variant = map[status] ?? "neutral";
  return <Badge variant={variant}>{status}</Badge>;
}

// ─── Score badge ───────────────────────────────────────────────────────────────

export function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 85 ? "text-[#C9A84C]" :
    score >= 70 ? "text-[#f0f0f0]" :
    "text-[#666]";
  return (
    <span className={`font-mono text-[11px] font-600 tabular-nums ${color}`}>
      {score}<span className="text-[9px] text-[#555]">/100</span>
    </span>
  );
}

// ─── Direction badge ───────────────────────────────────────────────────────────

export function DirectionBadge({ direction }: { direction: "LONG" | "SHORT" | "AUTO" }) {
  if (direction === "LONG") return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#22c55e]/10 text-[#22c55e] border border-[#22c55e]/20 font-mono text-[9px] tracking-widest rounded-sm">
      ▲ LONG
    </span>
  );
  if (direction === "SHORT") return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#ef4444]/10 text-[#ef4444] border border-[#ef4444]/20 font-mono text-[9px] tracking-widest rounded-sm">
      ▼ SHORT
    </span>
  );
  return <Badge variant="neutral">AUTO</Badge>;
}

// ─── Timeframe badge ───────────────────────────────────────────────────────────

export function TfBadge({ tf }: { tf: string }) {
  return (
    <span className="inline-flex px-1.5 py-0.5 bg-[#1c1c1c] border border-[#2e2e2e] font-mono text-[9px] text-[#666] rounded-sm">
      {tf}
    </span>
  );
}

// ─── Card ──────────────────────────────────────────────────────────────────────

export function Card({ children, className = "", onClick }: { children: ReactNode; className?: string; onClick?: () => void }) {
  return (
    <div className={`bg-[#111] border border-[#1e1e1e] rounded-sm ${className}`} onClick={onClick}>
      {children}
    </div>
  );
}

// ─── Section header ────────────────────────────────────────────────────────────

export function SectionHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between mb-4">
      <div>
        <h2 className="text-[13px] font-semibold text-[#f0f0f0] tracking-wide">{title}</h2>
        {subtitle && <p className="text-[11px] text-[#555] mt-0.5">{subtitle}</p>}
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}

// ─── MetricCard ────────────────────────────────────────────────────────────────

export function MetricCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <Card className={`px-4 py-3 ${highlight ? "gold-glow border-[#C9A84C]/20" : ""}`}>
      <div className="text-[10px] font-mono text-[#555] tracking-widest uppercase mb-1">{label}</div>
      <div className={`font-mono text-[18px] font-600 tabular-nums ${highlight ? "text-gold-gradient" : "text-[#f0f0f0]"}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-[#555] mt-0.5">{sub}</div>}
    </Card>
  );
}

// ─── Button ────────────────────────────────────────────────────────────────────

type BtnVariant = "gold" | "ghost" | "danger" | "outline";

export function Btn({
  children,
  variant = "ghost",
  size = "sm",
  onClick,
  className = "",
  disabled = false,
  title,
}: {
  children: ReactNode;
  variant?: BtnVariant;
  size?: "xs" | "sm" | "md";
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
  title?: string;
}) {
  const base = "inline-flex items-center justify-center font-mono tracking-wider transition-colors border";
  const sizes = { xs: "px-2 py-0.5 text-[9px]", sm: "px-3 py-1 text-[10px]", md: "px-4 py-1.5 text-[11px]" };
  const variants: Record<BtnVariant, string> = {
    gold: "bg-[#C9A84C]/10 text-[#C9A84C] border-[#C9A84C]/30 hover:bg-[#C9A84C]/20",
    ghost: "bg-transparent text-[#666] border-[#222] hover:text-[#aaa] hover:border-[#333]",
    danger: "bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/20 hover:bg-[#ef4444]/20",
    outline: "bg-transparent text-[#888] border-[#2e2e2e] hover:text-[#f0f0f0] hover:border-[#444]",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${base} ${sizes[size]} ${variants[variant]} rounded-sm ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"} ${className}`}
    >
      {children}
    </button>
  );
}

// ─── Tab bar ───────────────────────────────────────────────────────────────────

export function Tabs({
  tabs,
  active,
  onSelect,
}: {
  tabs: string[];
  active: string;
  onSelect: (t: string) => void;
}) {
  return (
    <div className="flex gap-0 border-b border-[#1e1e1e] mb-5">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onSelect(t)}
          className={`px-4 py-2 font-mono text-[10px] tracking-wider border-b-[1.5px] transition-colors ${
            active === t
              ? "text-[#C9A84C] border-[#C9A84C]"
              : "text-[#555] border-transparent hover:text-[#888]"
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

// ─── Filter chips ──────────────────────────────────────────────────────────────

export function FilterChips({
  options,
  active,
  onSelect,
}: {
  options: string[];
  active: string;
  onSelect: (o: string) => void;
}) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onSelect(o)}
          className={`px-2.5 py-1 font-mono text-[9px] tracking-wider border rounded-sm transition-colors ${
            active === o
              ? "bg-[#C9A84C]/10 text-[#C9A84C] border-[#C9A84C]/30"
              : "bg-transparent text-[#555] border-[#222] hover:text-[#888] hover:border-[#333]"
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

// ─── Demo data label ───────────────────────────────────────────────────────────

export function DemoLabel() {
  return (
    <span className="font-mono text-[8px] text-[#333] tracking-widest border border-[#222] px-1.5 py-0.5 rounded-sm">
      DEMO
    </span>
  );
}

// ─── Loading / Error / Empty states (dados reais — seções 37-39) ──────────────

export function LoadingState({ label = "Carregando dados do AlphaQuant X..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <span className="w-2 h-2 rounded-full bg-[#C9A84C] pulse-dot" />
      <span className="font-mono text-[10px] text-[#666] tracking-wider">{label}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 border border-[#3a1a1a] rounded-sm bg-[#1a0e0e]">
      <span className="font-mono text-[11px] text-[#ef4444] tracking-wide">DATA UNAVAILABLE</span>
      <span className="font-mono text-[10px] text-[#888] text-center max-w-md px-4">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="font-mono text-[10px] text-[#C9A84C] border border-[#C9A84C]/30 px-3 py-1.5 rounded-sm hover:bg-[#C9A84C]/10 transition-colors"
        >
          TENTAR DE NOVO
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2 border border-[#1a1a1a] rounded-sm">
      <span className="font-mono text-[11px] text-[#666] tracking-wide">{title}</span>
      {subtitle && <span className="font-mono text-[10px] text-[#444] text-center max-w-md px-4">{subtitle}</span>}
    </div>
  );
}

// ─── Regime badge ──────────────────────────────────────────────────────────────

export function RegimeBadge({ regime }: { regime: string }) {
  const map: Record<string, string> = {
    BULLISH: "text-[#22c55e]",
    BEARISH: "text-[#ef4444]",
    NEUTRAL: "text-[#888]",
    RANGING: "text-[#888]",
  };
  return (
    <span className={`font-mono text-[10px] tracking-wider ${map[regime] ?? "text-[#888]"}`}>
      {regime}
    </span>
  );
}

// ─── Inline stat ──────────────────────────────────────────────────────────────

export function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[9px] font-mono text-[#444] tracking-widest mb-0.5">{label}</div>
      <div className={`font-mono text-[12px] tabular-nums ${color ?? "text-[#f0f0f0]"}`}>{value}</div>
    </div>
  );
}

// ─── Progress bar ─────────────────────────────────────────────────────────────

export function ProgressBar({ value, max = 100, color = "#C9A84C" }: { value: number; max?: number; color?: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="w-full h-1 bg-[#1c1c1c] rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ─── Confluence score bar ─────────────────────────────────────────────────────

export function ConfluenceBar({ score }: { score: number }) {
  const color = score >= 80 ? "#C9A84C" : score >= 60 ? "#f59e0b" : "#666";
  return (
    <div className="flex items-center gap-2">
      <ProgressBar value={score} color={color} />
      <span className="font-mono text-[10px] tabular-nums" style={{ color }}>
        {score}
      </span>
    </div>
  );
}

// ─── Timeframe alignment row ──────────────────────────────────────────────────

export function TfAlignment({ data }: { data: { tf: string; regime: string }[] }) {
  return (
    <div className="flex items-center gap-2">
      {data.map(({ tf, regime }) => {
        const color =
          regime === "BULLISH" ? "#22c55e" :
          regime === "BEARISH" ? "#ef4444" :
          "#666";
        return (
          <div key={tf} className="flex flex-col items-center gap-0.5">
            <span className="font-mono text-[8px] text-[#444]">{tf}</span>
            <div className="w-4 h-4 rounded-sm flex items-center justify-center border" style={{ borderColor: color, background: `${color}12` }}>
              <span style={{ color }} className="text-[8px]">
                {regime === "BULLISH" ? "▲" : regime === "BEARISH" ? "▼" : "—"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Trade progress bar ───────────────────────────────────────────────────────

export function TradeProgress({ entry, current, stop, tp1 }: { entry: number; current: number; stop: number; tp1: number }) {
  const range = tp1 - stop;
  const entryPct = ((entry - stop) / range) * 100;
  const currentPct = Math.min(100, Math.max(0, ((current - stop) / range) * 100));
  const isProfit = current >= entry;
  return (
    <div className="relative h-2 bg-[#1c1c1c] rounded-full overflow-hidden">
      <div
        className="absolute top-0 h-full rounded-full transition-all"
        style={{
          left: `${entryPct}%`,
          width: `${Math.abs(currentPct - entryPct)}%`,
          backgroundColor: isProfit ? "#22c55e" : "#ef4444",
          opacity: 0.5,
        }}
      />
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-[#555]"
        style={{ left: `${entryPct}%` }}
      />
      <div
        className="absolute top-0 bottom-0 w-0.5 rounded"
        style={{ left: `${currentPct}%`, backgroundColor: isProfit ? "#22c55e" : "#ef4444" }}
      />
    </div>
  );
}
