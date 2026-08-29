import { useState } from "react";
import { Card, Tabs, Btn } from "../components/ui";

const SECTIONS = ["Account", "Trading", "Risk", "Telegram", "Scanner", "Notifications", "API", "System"];

const NOT_WIRED = "Configurações ainda não têm endpoint na API (sem persistência real) — alterações aqui não são salvas.";

export default function Settings() {
  const [tab, setTab] = useState("Account");

  return (
    <div className="p-5 lg:p-6 max-w-[800px]">
      <div className="flex items-center gap-2 mb-2">
        <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Settings</h1>
      </div>
      <div className="font-mono text-[9px] text-[#666] mb-5 border border-[#222] rounded-sm px-3 py-2 bg-[#111]">
        {NOT_WIRED}
      </div>

      <Tabs tabs={SECTIONS} active={tab} onSelect={setTab} />

      {tab === "Account" && <AccountSection />}
      {tab === "Trading" && <TradingSection />}
      {tab === "Risk" && <RiskSection />}
      {tab === "Telegram" && <TelegramSection />}
      {tab === "Scanner" && <ScannerSection />}
      {tab === "Notifications" && <NotificationsSection />}
      {tab === "API" && <ApiSection />}
      {tab === "System" && <SystemSection />}
    </div>
  );
}

function AccountSection() {
  return (
    <SettingsGroup title="Account">
      <Field label="Username" value="" />
      <Field label="Email" value="" />
      <div className="flex gap-2 mt-4">
        <Btn variant="gold" size="sm" disabled title={NOT_WIRED}>SAVE CHANGES</Btn>
      </div>
    </SettingsGroup>
  );
}

function TradingSection() {
  return (
    <SettingsGroup title="Trading">
      <ToggleField label="Auto-trading enabled" />
      <Field label="Default leverage" value="" />
      <div className="flex gap-2 mt-4">
        <Btn variant="gold" size="sm" disabled title={NOT_WIRED}>SAVE</Btn>
      </div>
    </SettingsGroup>
  );
}

function RiskSection() {
  return (
    <SettingsGroup title="Risk Management">
      <Field label="Max Risk / Trade" value="" />
      <Field label="Daily Loss Limit" value="" />
      <Field label="Min RR Required" value="" />
      <div className="flex gap-2 mt-4">
        <Btn variant="gold" size="sm" disabled title={NOT_WIRED}>SAVE RISK SETTINGS</Btn>
      </div>
    </SettingsGroup>
  );
}

function TelegramSection() {
  return (
    <SettingsGroup title="Telegram Integration">
      <div className="font-mono text-[9px] text-[#666] mb-3">
        Configurado via variáveis de ambiente no Render (TELEGRAM_BOT_TOKEN, TELEGRAM_SIGNALS_CHAT_ID) — não editável por aqui.
      </div>
      <Field label="Bot Token" value="•••• (env var)" readonly />
      <Field label="Chat ID" value="•••• (env var)" readonly />
      <div className="flex gap-2 mt-4">
        <Btn variant="outline" size="sm" disabled title={NOT_WIRED}>TEST MESSAGE</Btn>
      </div>
    </SettingsGroup>
  );
}

function ScannerSection() {
  return (
    <SettingsGroup title="Scanner Configuration">
      <div className="font-mono text-[9px] text-[#666] mb-3">
        Configurado via variáveis de ambiente no Render (SCAN_INTERVAL_MINUTES, SCAN_ASSETS, MIN/MAX_SYMBOLS, SCAN_CONCURRENCY) — não editável por aqui ainda.
      </div>
      <div className="flex gap-2 mt-4">
        <Btn variant="gold" size="sm" disabled title={NOT_WIRED}>SAVE</Btn>
      </div>
    </SettingsGroup>
  );
}

function NotificationsSection() {
  return (
    <SettingsGroup title="Notifications">
      <ToggleField label="Browser notifications" />
      <div className="flex gap-2 mt-4">
        <Btn variant="gold" size="sm" disabled title={NOT_WIRED}>SAVE</Btn>
      </div>
    </SettingsGroup>
  );
}

function ApiSection() {
  return (
    <SettingsGroup title="Exchange API">
      <div className="font-mono text-[9px] text-[#666] mb-3">
        O AlphaQuant X usa apenas dados públicos da Bybit (sem API key de exchange) — nada para configurar aqui.
      </div>
    </SettingsGroup>
  );
}

function SystemSection() {
  return (
    <SettingsGroup title="System">
      <Field label="Environment" value="" readonly />
      <div className="flex gap-2 mt-4">
        <Btn variant="danger" size="sm" disabled title={NOT_WIRED}>CLEAR LOGS</Btn>
      </div>
    </SettingsGroup>
  );
}

function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="font-mono text-[9px] text-[#C9A84C] tracking-widest mb-4">{title.toUpperCase()}</div>
      <div className="space-y-3">{children}</div>
    </Card>
  );
}

function Field({ label, value, readonly }: { label: string; value: string; readonly?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="font-mono text-[10px] text-[#555] shrink-0">{label}</label>
      <input
        defaultValue={value}
        placeholder="N/A"
        readOnly={readonly}
        className={`flex-1 max-w-[280px] bg-[#0d0d0d] border border-[#1e1e1e] rounded-sm px-3 py-2 font-mono text-[10px] text-right ${
          readonly ? "text-[#444] cursor-not-allowed" : "text-[#888] focus:border-[#C9A84C]/40 focus:outline-none"
        }`}
      />
    </div>
  );
}

function ToggleField({ label }: { label: string }) {
  const [on, setOn] = useState(false);
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] text-[#555]">{label}</span>
      <button
        onClick={() => setOn(!on)}
        className={`w-9 h-5 rounded-full transition-colors relative ${on ? "bg-[#C9A84C]/40" : "bg-[#222]"}`}
      >
        <div className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${on ? "left-4 bg-[#C9A84C]" : "left-0.5 bg-[#444]"}`} />
      </button>
    </div>
  );
}
