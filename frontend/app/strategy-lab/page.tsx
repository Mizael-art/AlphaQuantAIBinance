"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  Strategy,
  StrategyVersion,
  TestResult,
  activateStrategy,
  archiveStrategy,
  clearToken,
  createStrategy,
  deactivateStrategy,
  duplicateStrategy,
  getStrategyVersions,
  getToken,
  listStrategies,
  login,
  runBacktest,
  testStrategy,
  updateStrategy,
  type BacktestResult,
} from "@/lib/strategyLabApi";

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: "text-state-bullish",
  INACTIVE: "text-ink-500",
  ARCHIVED: "text-ink-500",
};

const VERSION_STATUS_COLOR: Record<string, string> = {
  VALID: "text-state-bullish",
  UNSUPPORTED_CONDITION: "text-state-warn",
  INVALID: "text-state-bearish",
};

const PROMPT_PLACEHOLDER = `NAME: Minha Estratégia
CONDITIONS:
  REGIME == BULLISH
  RSI14 < 40

STOP: SWING_LOW
TARGETS: RR 2.0, RR 3.0`;

export default function StrategyLabPage() {
  const [authed, setAuthed] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    setAuthed(!!getToken());
    setCheckingAuth(false);
  }, []);

  if (checkingAuth) return null;
  if (!authed) return <LoginGate onSuccess={() => setAuthed(true)} />;
  return <StrategyLabDashboard onLoggedOut={() => setAuthed(false)} />;
}

function LoginGate({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      onSuccess();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "falha ao entrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <h1 className="mb-1 text-xl font-semibold text-ink-100">Strategy Lab</h1>
      <p className="mb-6 text-sm text-ink-500">Área protegida — seção 24.</p>
      <form onSubmit={handleSubmit} className="rounded-lg border border-base-700 bg-base-900 p-6">
        <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">Usuário</label>
        <input
          className="mb-4 w-full rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100 outline-none focus:border-accent-teal"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">Senha</label>
        <input
          type="password"
          className="mb-4 w-full rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100 outline-none focus:border-accent-teal"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="mb-4 text-sm text-state-bearish">{error}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-accent-teal px-3 py-2 text-sm font-semibold text-base-950 transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}

function StrategyLabDashboard({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalStrategy, setModalStrategy] = useState<Strategy | "new" | null>(null);
  const [testingStrategy, setTestingStrategy] = useState<Strategy | null>(null);
  const [backtestingStrategy, setBacktestingStrategy] = useState<Strategy | null>(null);
  const [versionsStrategy, setVersionsStrategy] = useState<Strategy | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listStrategies();
      setStrategies(data.strategies);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        onLoggedOut();
        return;
      }
      setError(e instanceof Error ? e.message : "falha ao carregar estratégias");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAction(action: () => Promise<unknown>) {
    try {
      await action();
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        onLoggedOut();
        return;
      }
      alert(e instanceof Error ? e.message : "ação falhou");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-100">Strategy Lab</h1>
          <p className="text-sm text-ink-500">
            Estratégias criadas por PROMPT — sem alterar o core do scanner (seção 12).
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setModalStrategy("new")}
            className="rounded bg-accent-teal px-4 py-2 text-sm font-semibold text-base-950 hover:opacity-90"
          >
            + NOVA ESTRATÉGIA
          </button>
          <button
            onClick={() => {
              clearToken();
              onLoggedOut();
            }}
            className="rounded border border-base-700 px-4 py-2 text-sm text-ink-300 hover:bg-base-800"
          >
            Sair
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded border border-state-bearish/40 bg-state-bearish/10 p-4 text-sm text-state-bearish">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-ink-500">Carregando...</div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-base-700">
          <table className="w-full text-sm">
            <thead className="bg-base-900 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Versão</th>
                <th className="px-4 py-3">Modo</th>
                <th className="px-4 py-3">Runnable</th>
                <th className="px-4 py-3">Ações</th>
              </tr>
            </thead>
            <tbody>
              {strategies.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-ink-500">
                    Nenhuma estratégia ainda — clique em + NOVA ESTRATÉGIA.
                  </td>
                </tr>
              )}
              {strategies.map((s) => (
                <tr key={s.id} className="border-t border-base-700 bg-base-950">
                  <td className="px-4 py-3 text-ink-100">{s.name}</td>
                  <td className={`px-4 py-3 font-semibold ${STATUS_COLOR[s.status]}`}>{s.status}</td>
                  <td className="px-4 py-3">
                    <button
                      className={`underline decoration-dotted ${
                        VERSION_STATUS_COLOR[s.current_version?.status ?? ""] ?? "text-ink-300"
                      }`}
                      onClick={() => setVersionsStrategy(s)}
                      title={
                        s.current_version?.status !== "VALID"
                          ? (s.current_version?.errors || []).concat(s.current_version?.unsupported_conditions || []).join("; ")
                          : undefined
                      }
                    >
                      {s.current_version?.version_label} ({s.current_version?.status})
                    </button>
                  </td>
                  <td className="px-4 py-3 text-ink-300">{s.mode}</td>
                  <td className="px-4 py-3">{s.is_runnable ? "✅" : "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2 text-xs">
                      <button className="text-accent-cyan hover:underline" onClick={() => setModalStrategy(s)}>
                        Editar
                      </button>
                      <button className="text-accent-cyan hover:underline" onClick={() => setTestingStrategy(s)}>
                        Testar
                      </button>
                      <button className="text-accent-cyan hover:underline" onClick={() => setBacktestingStrategy(s)}>
                        Backtest
                      </button>
                      {s.status === "ACTIVE" ? (
                        <button
                          className="text-ink-300 hover:underline"
                          onClick={() => handleAction(() => deactivateStrategy(s.id))}
                        >
                          Desativar
                        </button>
                      ) : (
                        s.status === "INACTIVE" && (
                          <button
                            className="text-state-bullish hover:underline"
                            onClick={() => handleAction(() => activateStrategy(s.id))}
                          >
                            Ativar
                          </button>
                        )
                      )}
                      <button
                        className="text-ink-300 hover:underline"
                        onClick={() => handleAction(() => duplicateStrategy(s.id))}
                      >
                        Duplicar
                      </button>
                      {s.status !== "ARCHIVED" && (
                        <button
                          className="text-state-bearish hover:underline"
                          onClick={() => {
                            if (confirm(`Arquivar "${s.name}"? O histórico é preservado.`)) {
                              handleAction(() => archiveStrategy(s.id));
                            }
                          }}
                        >
                          Deletar
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalStrategy && (
        <StrategyModal
          strategy={modalStrategy === "new" ? null : modalStrategy}
          onClose={() => setModalStrategy(null)}
          onSaved={async () => {
            setModalStrategy(null);
            await refresh();
          }}
        />
      )}

      {testingStrategy && <TestModal strategy={testingStrategy} onClose={() => setTestingStrategy(null)} />}

      {backtestingStrategy && <BacktestModal strategy={backtestingStrategy} onClose={() => setBacktestingStrategy(null)} />}

      {versionsStrategy && <VersionsModal strategy={versionsStrategy} onClose={() => setVersionsStrategy(null)} />}
    </div>
  );
}

function StrategyModal({
  strategy,
  onClose,
  onSaved,
}: {
  strategy: Strategy | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!strategy;
  const [name, setName] = useState(strategy?.name ?? "");
  const [prompt, setPrompt] = useState(strategy?.current_version?.prompt_raw ?? "");
  const [mode, setMode] = useState(strategy?.mode ?? "SCANNER");
  const [active, setActive] = useState(strategy ? strategy.status === "ACTIVE" : true);
  const [changeNote, setChangeNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      if (isEdit) {
        await updateStrategy(strategy!.id, { prompt, mode, change_note: changeNote || undefined });
      } else {
        await createStrategy({ name, prompt, mode, active });
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-base-700 bg-base-900 p-6">
        <h2 className="mb-4 text-lg font-semibold text-ink-100">
          {isEdit ? `Editar: ${strategy!.name}` : "Nova Estratégia"}
        </h2>

        {!isEdit && (
          <>
            <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">Nome</label>
            <input
              className="mb-4 w-full rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100 outline-none focus:border-accent-teal"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </>
        )}

        <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">Prompt</label>
        <textarea
          className="mb-4 h-64 w-full rounded border border-base-700 bg-base-950 px-3 py-2 font-mono text-xs text-ink-100 outline-none focus:border-accent-teal"
          placeholder={PROMPT_PLACEHOLDER}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        <div className="mb-4 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">Modo</label>
            <select
              className="w-full rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="SCANNER">SCANNER</option>
              <option value="SWING">SWING</option>
              <option value="INTRADAY">INTRADAY</option>
              <option value="DAY_TRADE">DAY TRADE</option>
            </select>
          </div>
          {!isEdit && (
            <div className="flex items-end gap-2 pb-2">
              <input type="checkbox" id="active" checked={active} onChange={(e) => setActive(e.target.checked)} />
              <label htmlFor="active" className="text-sm text-ink-300">
                Ativa
              </label>
            </div>
          )}
        </div>

        {isEdit && (
          <>
            <label className="mb-1 block text-xs uppercase tracking-wide text-ink-500">
              Nota da alteração (opcional)
            </label>
            <input
              className="mb-4 w-full rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100 outline-none focus:border-accent-teal"
              placeholder="ex.: deixando mais permissiva — poucas entradas na v1"
              value={changeNote}
              onChange={(e) => setChangeNote(e.target.value)}
            />
            <p className="mb-4 text-xs text-ink-500">
              Salvar cria uma nova versão ({strategy!.version_count + 1}ª) — a versão atual nunca é sobrescrita.
            </p>
          </>
        )}

        {error && <div className="mb-4 text-sm text-state-bearish">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-base-700 px-4 py-2 text-sm text-ink-300 hover:bg-base-800">
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !prompt.trim() || (!isEdit && !name.trim())}
            className="rounded bg-accent-teal px-4 py-2 text-sm font-semibold text-base-950 hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Salvando..." : isEdit ? "Salvar nova versão" : "Criar Estratégia"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TestModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [asset, setAsset] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [result, setResult] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleTest() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await testStrategy(strategy.id, asset, timeframe));
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao testar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-lg border border-base-700 bg-base-900 p-6">
        <h2 className="mb-1 text-lg font-semibold text-ink-100">Testar: {strategy.name}</h2>
        <p className="mb-4 text-xs text-ink-500">
          Roda contra o contexto de mercado atual — não envia Telegram nem cria operação.
        </p>

        <div className="mb-4 flex gap-3">
          <input
            className="flex-1 rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
            value={asset}
            onChange={(e) => setAsset(e.target.value.toUpperCase())}
            placeholder="BTCUSDT"
          />
          <select
            className="rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {["15m", "1h", "4h", "1d"].map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
          <button
            onClick={handleTest}
            disabled={loading}
            className="rounded bg-accent-teal px-4 py-2 text-sm font-semibold text-base-950 hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "..." : "Testar"}
          </button>
        </div>

        {error && <div className="mb-4 text-sm text-state-bearish">{error}</div>}

        {result && !result.runnable && (
          <div className="rounded border border-state-warn/40 bg-state-warn/10 p-4 text-sm">
            <div className="font-semibold text-state-warn">{result.status}</div>
            {(result.errors || []).map((e, i) => (
              <div key={i} className="text-ink-300">
                {e}
              </div>
            ))}
            {(result.unsupported_conditions || []).map((e, i) => (
              <div key={i} className="text-ink-300">
                {e}
              </div>
            ))}
          </div>
        )}

        {result && result.runnable && (
          <div className="rounded border border-base-700 bg-base-950 p-4 text-sm">
            <div className={`mb-2 font-semibold ${result.matched ? "text-state-bullish" : "text-ink-500"}`}>
              {result.matched ? `🟢 BATEU (${result.direction})` : "— não bateu agora"}
            </div>
            <div className="mb-2 text-ink-300">Progresso: {result.progress}%</div>
            {result.entry != null && (
              <div className="text-ink-300">
                Entrada: {result.entry} · Stop: {result.stop}
              </div>
            )}
            {result.notes && <div className="mt-1 text-state-warn">{result.notes}</div>}
            <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
              <div>
                <div className="mb-1 text-ink-500">Condições atendidas</div>
                {(result.conditions_met || []).map((c, i) => (
                  <div key={i} className="text-state-bullish">
                    ✓ {c}
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 text-ink-500">Faltando</div>
                {(result.conditions_missing || []).map((c, i) => (
                  <div key={i} className="text-ink-500">
                    ✗ {c}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="rounded border border-base-700 px-4 py-2 text-sm text-ink-300 hover:bg-base-800">
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}

function BacktestModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [asset, setAsset] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [lookback, setLookback] = useState(60);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await runBacktest(strategy.id, asset, timeframe, lookback));
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao rodar backtest");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-lg border border-base-700 bg-base-900 p-6">
        <h2 className="mb-1 text-lg font-semibold text-ink-100">Backtest: {strategy.name}</h2>
        <p className="mb-4 text-xs text-ink-500">
          Sem lookahead, bar a bar, sobre o histórico já persistido para esse ativo/timeframe. Monte Carlo,
          Walk Forward e Sensitivity ficam disponíveis via API (<code>/strategies/{strategy.id}/backtest/*</code>) —
          ainda sem painel dedicado aqui.
        </p>

        <div className="mb-4 flex gap-3">
          <input
            className="flex-1 rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
            value={asset}
            onChange={(e) => setAsset(e.target.value.toUpperCase())}
            placeholder="BTCUSDT"
          />
          <select
            className="rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {["15m", "1h", "4h", "1d"].map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
          <input
            type="number"
            className="w-20 rounded border border-base-700 bg-base-950 px-3 py-2 text-sm text-ink-100"
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
            title="lookback (candles)"
          />
          <button
            onClick={handleRun}
            disabled={loading}
            className="rounded bg-accent-teal px-4 py-2 text-sm font-semibold text-base-950 hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "..." : "Rodar"}
          </button>
        </div>

        {error && <div className="mb-4 text-sm text-state-bearish">{error}</div>}

        {result && (
          <div className="rounded border border-base-700 bg-base-950 p-4 text-sm">
            <div className="mb-2 text-xs text-ink-500">
              {result.period.candles} candles · {new Date(result.period.start).toLocaleDateString("pt-BR")} –{" "}
              {new Date(result.period.end).toLocaleDateString("pt-BR")}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Trades" value={result.stats.trades} />
              <Stat label="Win rate" value={`${(result.stats.win_rate * 100).toFixed(1)}%`} />
              <Stat label="Payoff" value={result.stats.payoff.toFixed(2)} />
              <Stat label="Profit factor" value={result.stats.profit_factor.toFixed(2)} />
              <Stat label="Expectancy (R)" value={result.stats.expectancy.toFixed(2)} />
              <Stat label="Max DD (R)" value={result.stats.max_drawdown.toFixed(2)} />
            </div>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="rounded border border-base-700 px-4 py-2 text-sm text-ink-300 hover:bg-base-800">
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-ink-500">{label}</div>
      <div className="text-ink-100">{value}</div>
    </div>
  );
}

function VersionsModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const [versions, setVersions] = useState<StrategyVersion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStrategyVersions(strategy.id)
      .then((d) => setVersions(d.versions))
      .finally(() => setLoading(false));
  }, [strategy.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-base-700 bg-base-900 p-6">
        <h2 className="mb-4 text-lg font-semibold text-ink-100">Histórico de versões: {strategy.name}</h2>
        {loading ? (
          <div className="text-sm text-ink-500">Carregando...</div>
        ) : (
          <div className="flex flex-col gap-3">
            {versions
              .slice()
              .reverse()
              .map((v) => (
                <div key={v.id} className="rounded border border-base-700 bg-base-950 p-4">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-semibold text-ink-100">
                      {v.version_label} {v.is_current && <span className="text-accent-teal">(atual)</span>}
                    </span>
                    <span className={VERSION_STATUS_COLOR[v.status] ?? "text-ink-300"}>{v.status}</span>
                  </div>
                  {v.change_note && <div className="mb-1 text-xs text-ink-500">Nota: {v.change_note}</div>}
                  <div className="mb-1 text-xs text-ink-500">
                    {v.author ? `${v.author} · ` : ""}
                    {new Date(v.created_at).toLocaleString("pt-BR")}
                  </div>
                  <pre className="whitespace-pre-wrap rounded bg-base-900 p-2 text-xs text-ink-300">{v.prompt_raw}</pre>
                </div>
              ))}
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <button onClick={onClose} className="rounded border border-base-700 px-4 py-2 text-sm text-ink-300 hover:bg-base-800">
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
