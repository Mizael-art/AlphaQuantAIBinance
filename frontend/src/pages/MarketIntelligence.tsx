import { useState } from "react";
import { Card, RegimeBadge, LoadingState, ErrorState } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";

const TIMEFRAMES = ["15m", "1h", "4h", "1d"];
const WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"];

export default function MarketIntelligence() {
  const [asset, setAsset] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("4h");

  const { data, loading, error, reload } = useApi(() => api.marketData(asset, timeframe), [asset, timeframe]);

  const ind = data?.indicators;
  const regime = data?.structure?.regime;
  const events = data?.structure?.events || [];

  return (
    <div className="p-5 lg:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-[15px] font-semibold text-[#f0f0f0]">Market Intelligence</h1>
          <p className="text-[11px] text-[#555]">Engine data — structure and momentum, calculado em tempo real via Bybit.</p>
        </div>
      </div>

      <Card className="p-4 mb-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            {WATCHLIST.map((a) => (
              <button
                key={a}
                onClick={() => setAsset(a)}
                className={`font-mono text-[11px] px-2 py-1 rounded-sm border transition-colors ${
                  asset === a ? "text-[#C9A84C] border-[#C9A84C]/30 bg-[#C9A84C]/10" : "text-[#666] border-[#222] hover:text-[#aaa]"
                }`}
              >
                {a}
              </button>
            ))}
            {regime && <RegimeBadge regime={regime} />}
          </div>
          <div className="flex gap-2">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 font-mono text-[9px] rounded-sm border transition-colors ${
                  timeframe === tf ? "text-[#C9A84C] border-[#C9A84C]/30 bg-[#C9A84C]/10" : "text-[#555] border-[#222] hover:text-[#888]"
                }`}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {loading && !data && <LoadingState label={`Analisando ${asset} ${timeframe}...`} />}
      {error && <ErrorState message={error} onRetry={reload} />}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Panel title="STRUCTURE" items={[
                { label: "Regime", value: regime || "N/A" },
                { label: "Last Close", value: data.last_close != null ? String(data.last_close) : "N/A" },
                { label: "Candles Analyzed", value: String(data.candles_analyzed ?? "N/A") },
              ]} />

              <Panel title="MOMENTUM" items={[
                { label: "RSI 14", value: fmt(ind?.rsi14) },
                { label: "EMA 20", value: fmt(ind?.ema20) },
                { label: "EMA 50", value: fmt(ind?.ema50) },
                { label: "EMA 100", value: fmt(ind?.ema100) },
                { label: "EMA 200", value: fmt(ind?.ema200) },
                { label: "ATR 14", value: fmt(ind?.atr14) },
                { label: "MACD", value: fmt(ind?.macd) },
                { label: "MACD Signal", value: fmt(ind?.macd_signal) },
              ]} />

              <Panel title="LIQUIDITY" items={[]} unavailable />
              <Panel title="SMART MONEY" items={[]} unavailable />
              <Panel title="VOLUME" items={[]} unavailable />
              <Panel title="DERIVATIVES" items={[]} unavailable />
            </div>
          </div>

          <div className="space-y-4">
            <Card className="p-4">
              <div className="font-mono text-[9px] text-[#C9A84C] tracking-widest mb-3">RECENT STRUCTURE EVENTS</div>
              {events.length === 0 && <span className="font-mono text-[9px] text-[#444]">Nenhum evento recente registrado.</span>}
              <div className="space-y-2">
                {events.map((e: any, i: number) => (
                  <div key={i} className="text-[9px] font-mono text-[#666]">
                    {e.type || JSON.stringify(e)}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? "N/A" : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function Panel({ title, items, unavailable }: { title: string; items: { label: string; value: string }[]; unavailable?: boolean }) {
  return (
    <Card className="p-4">
      <div className="font-mono text-[9px] text-[#C9A84C] tracking-widest mb-3">{title}</div>
      {unavailable ? (
        <span className="font-mono text-[9px] text-[#444]">DATA_UNAVAILABLE — não implementado no backend ainda.</span>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.label} className="flex items-center justify-between">
              <span className="font-mono text-[9px] text-[#555]">{item.label}</span>
              <span className="font-mono text-[9px] text-[#888] tabular-nums">{item.value}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
