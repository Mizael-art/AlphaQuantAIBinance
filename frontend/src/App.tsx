import { useState } from "react";
import Overview from "./pages/Overview";
import Scanner from "./pages/Scanner";
import Opportunities from "./pages/Opportunities";
import Setups from "./pages/Setups";
import Playbooks from "./pages/Playbooks";
import StrategyLab from "./pages/StrategyLab";
import OpenTrades from "./pages/OpenTrades";
import TradeHistory from "./pages/TradeHistory";
import Performance from "./pages/Performance";
import MarketIntelligence from "./pages/MarketIntelligence";
import SystemHealth from "./pages/SystemHealth";
import Settings from "./pages/Settings";

export type Page =
  | "overview"
  | "scanner"
  | "opportunities"
  | "setups"
  | "playbooks"
  | "strategy-lab"
  | "open-trades"
  | "trade-history"
  | "performance"
  | "market-intelligence"
  | "system-health"
  | "settings";

const NAV = [
  { id: "overview", label: "Overview", icon: GridIcon },
  { id: "scanner", label: "Live Scanner", icon: ScanIcon },
  { id: "opportunities", label: "Opportunities", icon: StarIcon },
  { id: "setups", label: "Setups", icon: LayersIcon },
  { id: "playbooks", label: "Playbooks", icon: BookIcon },
  { id: "strategy-lab", label: "Strategy Lab", icon: FlaskIcon },
  { id: "open-trades", label: "Open Trades", icon: ActivityIcon },
  { id: "trade-history", label: "Trade History", icon: ClockIcon },
  { id: "performance", label: "Performance", icon: ChartIcon },
  { id: "market-intelligence", label: "Market Intel", icon: BrainIcon },
  { id: "system-health", label: "System Health", icon: ServerIcon },
  { id: "settings", label: "Settings", icon: GearIcon },
] as const;

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const renderPage = () => {
    switch (page) {
      case "overview": return <Overview onNavigate={setPage} />;
      case "scanner": return <Scanner />;
      case "opportunities": return <Opportunities />;
      case "setups": return <Setups />;
      case "playbooks": return <Playbooks />;
      case "strategy-lab": return <StrategyLab />;
      case "open-trades": return <OpenTrades />;
      case "trade-history": return <TradeHistory />;
      case "performance": return <Performance />;
      case "market-intelligence": return <MarketIntelligence />;
      case "system-health": return <SystemHealth />;
      case "settings": return <Settings />;
    }
  };

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-[#f0f0f0] overflow-hidden">
      {/* Sidebar — desktop */}
      <aside className="hidden lg:flex flex-col w-[220px] shrink-0 bg-[#0d0d0d] border-r border-[#1e1e1e]">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 h-14 border-b border-[#1e1e1e]">
          <div className="flex items-center gap-1.5">
            <div className="w-6 h-6 relative">
              <div className="absolute inset-0 border border-[#C9A84C] rotate-45 scale-75" />
              <div className="absolute inset-[3px] bg-[#C9A84C] rotate-45 scale-50" />
            </div>
            <span className="font-mono text-[13px] font-700 tracking-widest text-[#C9A84C] uppercase">
              AlphaQuant
            </span>
            <span className="font-mono text-[10px] font-700 text-[#888] tracking-widest ml-0.5">X</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto no-scrollbar">
          {NAV.map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => setPage(id as Page)}
                className={`w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors relative group ${
                  active
                    ? "text-[#C9A84C] bg-[#C9A84C]/5"
                    : "text-[#666] hover:text-[#aaa] hover:bg-white/[0.02]"
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-1 bottom-1 w-[2px] bg-[#C9A84C] rounded-r" />
                )}
                <Icon size={14} active={active} />
                <span className="text-[12px] font-medium tracking-wide">{label}</span>
              </button>
            );
          })}
        </nav>

        {/* Footer status */}
        <div className="border-t border-[#1e1e1e] px-5 py-4 space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] pulse-dot" />
            <span className="font-mono text-[10px] text-[#22c55e] tracking-wider">SYSTEM ONLINE</span>
          </div>
          <div className="font-mono text-[10px] text-[#444]">Last scan: 14:32:07</div>
          <div className="font-mono text-[10px] text-[#444]">Next scan: 14:47:00</div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <Topbar page={page} onMobileMenu={() => setMobileMenuOpen(true)} />

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-[#0a0a0a]">
          {renderPage()}
        </main>

        {/* Mobile bottom nav */}
        <nav className="lg:hidden flex border-t border-[#1e1e1e] bg-[#0d0d0d]">
          {[
            { id: "overview", label: "Overview", icon: GridIcon },
            { id: "scanner", label: "Scanner", icon: ScanIcon },
            { id: "opportunities", label: "Opps", icon: StarIcon },
            { id: "open-trades", label: "Trades", icon: ActivityIcon },
            { id: "settings", label: "More", icon: GearIcon },
          ].map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                onClick={() => setPage(id as Page)}
                className={`flex-1 flex flex-col items-center gap-1 py-3 transition-colors ${
                  active ? "text-[#C9A84C]" : "text-[#555]"
                }`}
              >
                <Icon size={16} active={active} />
                <span className="text-[9px] font-medium tracking-wide">{label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

function Topbar({ page, onMobileMenu }: { page: Page; onMobileMenu: () => void }) {
  const pageLabels: Record<Page, string> = {
    overview: "Overview",
    scanner: "Live Scanner",
    opportunities: "Opportunities",
    setups: "Setups",
    playbooks: "Playbooks",
    "strategy-lab": "Strategy Lab",
    "open-trades": "Open Trades",
    "trade-history": "Trade History",
    performance: "Performance",
    "market-intelligence": "Market Intelligence",
    "system-health": "System Health",
    settings: "Settings",
  };

  return (
    <header className="h-14 flex items-center justify-between px-5 border-b border-[#1e1e1e] bg-[#0d0d0d] shrink-0">
      {/* Left: mobile logo + page title */}
      <div className="flex items-center gap-4">
        <button className="lg:hidden" onClick={onMobileMenu}>
          <MenuIcon />
        </button>
        <span className="text-[12px] font-mono text-[#555] tracking-widest uppercase hidden lg:block">
          {pageLabels[page]}
        </span>
        <div className="lg:hidden flex items-center gap-1.5">
          <div className="w-4 h-4 relative">
            <div className="absolute inset-0 border border-[#C9A84C] rotate-45 scale-75" />
            <div className="absolute inset-[2px] bg-[#C9A84C] rotate-45 scale-50" />
          </div>
          <span className="font-mono text-[11px] font-700 text-[#C9A84C] tracking-widest">AQ X</span>
        </div>
      </div>

      {/* Center: market data strip */}
      <div className="hidden md:flex items-center gap-5">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] pulse-dot" />
          <span className="font-mono text-[10px] text-[#22c55e] tracking-wider">ONLINE</span>
        </div>
        <Divider />
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-[#555]">BTC</span>
          <span className="font-mono text-[11px] text-[#f0f0f0] tabular-nums">$67,842</span>
          <span className="font-mono text-[10px] text-[#22c55e]">+2.14%</span>
        </div>
        <Divider />
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-[#555]">REGIME</span>
          <span className="font-mono text-[10px] text-[#C9A84C] tracking-wider">BULLISH</span>
        </div>
        <Divider />
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-[#555]">SCANNER</span>
          <span className="font-mono text-[10px] text-[#22c55e]">ACTIVE</span>
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-3">
        <button className="relative p-1.5 text-[#555] hover:text-[#888] transition-colors">
          <BellIcon />
          <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-[#C9A84C]" />
        </button>
        <div className="w-7 h-7 rounded-full bg-[#1a1a1a] border border-[#2e2e2e] flex items-center justify-center">
          <span className="font-mono text-[10px] text-[#C9A84C]">AQ</span>
        </div>
      </div>
    </header>
  );
}

function Divider() {
  return <span className="w-px h-3 bg-[#2e2e2e]" />;
}

// ─── Icon components ────────────────────────────────────────────────────────

function GridIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <rect x="1" y="1" width="5" height="5" rx="0.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <rect x="8" y="1" width="5" height="5" rx="0.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <rect x="1" y="8" width="5" height="5" rx="0.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <rect x="8" y="8" width="5" height="5" rx="0.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
    </svg>
  );
}
function ScanIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <circle cx="7" cy="7" r="2" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <line x1="7" y1="1" x2="7" y2="2.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <line x1="7" y1="11.5" x2="7" y2="13" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <line x1="1" y1="7" x2="2.5" y2="7" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
      <line x1="11.5" y1="7" x2="13" y2="7" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.2" />
    </svg>
  );
}
function StarIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <polygon points="7,1.5 8.5,5.5 13,5.5 9.5,8.5 10.5,12.5 7,10 3.5,12.5 4.5,8.5 1,5.5 5.5,5.5" stroke={active ? "#C9A84C" : "currentColor"} strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  );
}
function LayersIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M1 4.5L7 2L13 4.5L7 7L1 4.5Z" stroke={c} strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M1 7.5L7 10L13 7.5" stroke={c} strokeWidth="1.1" strokeLinecap="round" />
      <path d="M1 10.5L7 13L13 10.5" stroke={c} strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}
function BookIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M2 2h5v10H2z" stroke={c} strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M7 2h5v10H7z" stroke={c} strokeWidth="1.1" strokeLinejoin="round" />
      <line x1="7" y1="2" x2="7" y2="12" stroke={c} strokeWidth="1.1" />
    </svg>
  );
}
function FlaskIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M5 1h4M5 1v5L2 12h10L9 6V1" stroke={c} strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 9.5h7" stroke={c} strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}
function ActivityIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <polyline points="1,7 4,4 6,10 8,3 10,7 13,7" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ClockIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5.5" stroke={c} strokeWidth="1.1" />
      <polyline points="7,4 7,7 9.5,9" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
function ChartIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M1 13V5l3-3 3 3 3-5 3 3v10" stroke={c} strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function BrainIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M5 1.5C3 1.5 1 3 1 5.5c0 1.5.7 2.7 1.7 3.5L3 12h4V1.5H5Z" stroke={c} strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M9 1.5C11 1.5 13 3 13 5.5c0 1.5-.7 2.7-1.7 3.5L11 12H7V1.5h2Z" stroke={c} strokeWidth="1.1" strokeLinejoin="round" />
      <line x1="7" y1="1.5" x2="7" y2="12" stroke={c} strokeWidth="1.1" />
    </svg>
  );
}
function ServerIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <rect x="1" y="1" width="12" height="4" rx="0.5" stroke={c} strokeWidth="1.1" />
      <rect x="1" y="9" width="12" height="4" rx="0.5" stroke={c} strokeWidth="1.1" />
      <line x1="3.5" y1="3" x2="3.5" y2="3" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="3.5" y1="11" x2="3.5" y2="11" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
function GearIcon({ size = 14, active }: { size?: number; active?: boolean }) {
  const c = active ? "#C9A84C" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="2" stroke={c} strokeWidth="1.1" />
      <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.5 2.5l1 1M10.5 10.5l1 1M11.5 2.5l-1 1M3.5 10.5l-1 1" stroke={c} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
function BellIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M7 1.5C4.8 1.5 3 3.3 3 5.5V9l-1 1.5h10L11 9V5.5C11 3.3 9.2 1.5 7 1.5Z" stroke="currentColor" strokeWidth="1.1" />
      <path d="M5.5 11.5a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}
function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M2 4.5h14M2 9h14M2 13.5h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
