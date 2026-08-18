# ARCHITECTURE.md — ALPHAQUANT X

## Visão geral

O AlphaQuant X é um Trading Intelligence Operating System, não um site. O
frontend (Vercel) é apenas a interface; a inteligência real vive na API
(Render) e, principalmente, no Worker 24/7 (Render Background Worker), que
continua rodando mesmo sem ninguém com o site aberto.

```
Frontend (Vercel)  --->  API (Render / FastAPI)  --->  PostgreSQL (Render)
                                 |
                                 |--- Webhook TradingView (autenticado, só registra evento)
                                 |
                       Worker 24/7 (Render Background Worker)
                                 |
                       Market Data (Binance/TradingView) ---> Engines ---> Telegram
```

## Pacote compartilhado — `shared/alphaquant_core`

API e Worker leem e escrevem no mesmo banco. Para não duplicar schema e
configuração, `db/models.py`, `db/session.py` e `core/config.py` vivem em
um pacote local instalável (`-e ../shared`) usado por ambos os serviços.
Isso evita que o schema da API e o schema do Worker divirjam.

## Data Engine (Fase 3 — implementado)

`shared/alphaquant_core/engines/`:

- `data_engine.py` — `BinanceMarketDataClient`, apenas endpoints públicos
  (`/api/v3/klines`, `/api/v3/ticker/price`, `/api/v3/depth`), sem API key,
  erros de rede/HTTP encapsulados em `BinanceRequestError` (nunca fabrica
  dado no lugar de uma falha).
- `indicators.py` — EMA20/50/100/200, RSI14 (Wilder), ATR14 (Wilder),
  MACD 12/26/9, volume médio 20, calculados manualmente com pandas (sem
  dependência de pandas-ta).
- `structure.py` — detecção de swings (janela configurável), rotulagem
  HH/HL/LH/LL e eventos BOS (continuação) / CHOCH (mudança de caráter).
- `orchestrator.py` (`analyze_asset`) — encadeia coleta → persistência →
  indicadores → estrutura e devolve o JSON padronizado consumido pelo
  Worker e pelo endpoint de debug `GET /market-data/{symbol}`.
- `services/candle_service.py` — upsert idempotente de candles
  (`ON CONFLICT` por `asset_id + timeframe + timestamp`, nunca duplica).

O Worker (`worker/app/main.py`) chama `scan_symbol` (Data Engine + Playbook
Engine encadeados) para cada combinação de `SCAN_ASSETS` × `SCAN_TIMEFRAMES`
a cada ciclo; falhas de coleta são registradas em `scanner_events` e
refletidas em `system_health` como `DEGRADED`, sem derrubar o processo.
Playbooks batidos (`matched=True`) são logados com direção/entry/stop.

## Playbook Engine (Fase 4 — implementado)

`shared/alphaquant_core/playbooks/`:

- `base.py` — `PlaybookContext` (candles + indicadores + swings + regime +
  FVGs + order blocks + sweep + regime HTF opcional + razão de contração
  de volatilidade, calculados uma única vez por ciclo) e `PlaybookResult`
  (`matched`, `direction`, `progress` 0-100%, `conditions_met`/
  `conditions_missing`, `entry`/`stop` sugeridos) — o contrato comum que
  todo playbook implementa.
- Os 10 playbooks oficiais, cada um em seu próprio arquivo
  (`trend_continuation.py`, `liquidity_sweep_reversal.py`,
  `order_block_reaction.py`, `fvg_retracement.py`, `breakout_retest.py`,
  `wyckoff_spring.py`, `wyckoff_upthrust.py`, `htf_continuation.py`,
  `compression_breakout.py`, `open_range_breakout.py`) — cada um devolve
  uma lista explícita de condições atendidas/faltantes, nunca só um
  booleano.
- `engine.py` — `build_context()` monta o contexto uma única vez
  (indicadores + estrutura + liquidez) e `evaluate_all()` roda todos os
  10 playbooks contra ele.
- `runner.py` — `scan_symbol()` combina a etapa DATA (via
  `orchestrator.fetch_and_persist`, compartilhada com o Data Engine — não
  busca os mesmos candles duas vezes) com `build_context` + `evaluate_all`.

`engines/liquidity.py` dá suporte aos playbooks: `detect_fair_value_gaps`
(FVG de 3 candles, com `filled` calculado por fechamento que atravessa o
gap inteiro — não por um simples toque), `detect_order_blocks` (última
candle de cor oposta antes de um swing confirmado) e
`detect_latest_liquidity_sweep` (wick além de um swing anterior + fecha-
mento de volta do lado certo). `indicators.atr_contraction_ratio` mede
squeeze de volatilidade excluindo a candle mais recente do cálculo (para
não deixar o próprio range do rompimento mascarar a compressão que o
precedeu) — usado pelos playbooks Wyckoff Spring/Upthrust e Compression
Breakout.

Todo `PlaybookResult` com `matched=False` e `progress>0` é, por definição,
material bruto do Future Opportunity Engine (Fase 11) — ver
`docs/PROJECT_PLAN.md` para os detalhes de como isso será persistido.

## Scoring Engine (Fase 5 — implementado)

Segue rigorosamente a ordem da seção 68: `ENTRY -> STOP -> TARGETS -> RR
-> SCORE`.

- `engines/targets.py` (`compute_targets`) — projeta TP1/TP2/TP3 a partir
  de swings estruturais reais (o próximo swing HIGH acima da entrada, para
  LONG; o próximo LOW abaixo, para SHORT), descartando qualquer swing a
  menos de 1R de distância (ruído, não um alvo útil —
  `MIN_RR_FOR_STRUCTURAL_TARGET`). Completa com múltiplos de R (2R/3R/4R)
  quando não há swings suficientes, e marca a origem de cada alvo
  (`structural` vs `r_multiple`) para nunca confundir os dois. RR é
  calculado sobre o TP1. Devolve `None` se o stop não representar uma
  invalidação real (risco ≤ 0).
- `engines/scoring.py` (`compute_score`) — Contexto (35: regime alinhado,
  confirmação HTF, RSI não esticado) + Estrutura (35: playbook confirmado,
  zonas de suporte ativas) + Execução (30: qualidade do RR, alvos
  estruturais reais) + bônus (+5: playbook confirmado com RR excepcional
  >5), sempre `min(100, bruto)`. Cada ponto vem de um `ScoreCriterion`
  nomeado (`category`, `name`, `points`, `max_points`) — nunca um número
  isolado, exatamente o que a Auditoria (seção 57) exige.
- `services/opportunity_service.py` (`upsert_opportunity`) — cria ou
  atualiza (por `asset+timeframe+playbook+direction`, nunca duplica) a
  `Opportunity` com os campos de score/targets/RR preenchidos, e
  reescreve as linhas de `evidence` (uma por critério de Score) a cada
  ciclo. `CONFIDENCE` é calculado à parte (`compute_confidence`) e mede
  qualidade/completude dos DADOS disponíveis — nunca é confundido com
  Score (qualidade da evidência) nem Progress (% de condições do
  playbook), conforme a independência exigida pela seção 25.
- `playbooks/runner.py::scan_and_score` — combina tudo: só playbooks com
  `matched=True` viram `Opportunity` persistida; resultados parciais
  ficam para a Fase 11. `Opportunity.status` permanece sempre
  `FORMATION` — decidir `CONFIRMED`/`INVALIDATED` é do Quality Filter e
  do Decision Engine (Fases 6-7), não desta função.

Duas decisões de design que só ficaram claras testando contra Postgres
real (vale o registro): (1) valores `numpy.float64` vazando de qualquer
engine até uma coluna do banco quebram a adaptação do driver psycopg2 com
um erro cabeludo (`InvalidSchemaName: schema "np" does not exist`) — por
isso `opportunity_service.py` tem uma função `_as_float()` que converte
tudo para `float` nativo antes de gravar, e `liquidity.py` foi corrigido
para nunca devolver `numpy.float64` em `FairValueGap.low/high`; (2) um
swing estrutural muito próximo da entrada não é um alvo útil — é só ruído
de faixa lateral — daí o filtro `MIN_RR_FOR_STRUCTURAL_TARGET` em
`targets.py`.

## Quality Filter (Fase 6 — implementado)

`engines/quality_filter.py` (`evaluate_quality`) — mesmo um Score 95+ é
REPROVADO se qualquer um dos bloqueios absolutos da seção 27 disparar:

- nenhum Playbook confirmado (`playbook_result.matched is False`);
- stop não representa uma invalidação real (`target_result is None`,
  risco ≤ 0);
- RR abaixo do mínimo exigido **pelo playbook específico** (não um valor
  fixo no código — lido de `playbooks.minimum_rr`, já existente desde a
  Fase 1/seed da Fase 4; cai em 2.0 se o playbook não estiver cadastrado);
- Score abaixo do mínimo exigido pelo playbook (`playbooks.minimum_score`,
  padrão 70.0);
- dados insuficientes (`confidence == "BAIXA"`, calculado pela mesma
  `compute_confidence` da Fase 5).

Todos os motivos de reprovação são reportados juntos (nunca só o
primeiro), e o veredito (`approved` + `reasons`) é gravado tanto em
`Opportunity.audit_snapshot["quality_filter"]` quanto numa linha própria
de `evidence` (`category="QUALITY_FILTER"`) — para o Decision Engine
(Fase 7) consumir sem recalcular nada, e para a Auditoria (seção 57)
sempre ter a resposta pronta. **Não decide `status`/`decision`** — isso
continua sendo do Decision Engine; toda `Opportunity` ainda fica
`FORMATION` depois do Quality Filter, aprovada ou não.

`playbooks/runner.py::scan_and_score` busca `minimum_score`/`minimum_rr`
na tabela `playbooks` por nome (`_playbook_thresholds`) antes de chamar
`evaluate_quality` — importante para quem for ajustar o rigor de um
playbook específico (ex.: exigir RR mínimo 3 só para o Open Range
Breakout, ainda EXPERIMENTAL): é uma linha no banco, não uma mudança de
código.

## Decision Engine (Fase 7 — implementado)

`engines/decision.py` (`make_decision`) fecha o pipeline principal da
seção 68 (`DATA -> ... -> QUALITY FILTER -> DECISION ENGINE`). Regra:

- Quality Filter reprovou -> **REPROVAR** (usa os mesmos motivos do
  Quality Filter, sem reinterpretar — ele já é a fonte da verdade sobre
  bloqueios absolutos).
- Quality Filter aprovou **e** `confidence == "ALTA"` -> **ENTRAR**.
- Quality Filter aprovou mas `confidence` não é `"ALTA"` (ex.: HTF
  indisponível neste ciclo, ver `compute_confidence` na Fase 5) ->
  **ESPERAR**: a evidência já passou pelos bloqueios absolutos, só falta
  um dado que aumentaria a confiança da decisão — não é reprovação, é
  "ainda não".

Nunca devolve `BUY`/`SELL`/`LONG`/`SHORT` isolado (seção 28) — a direção
já vem do `PlaybookResult`; o Decision Engine só decide **se agir**.

`Opportunity.status`/`.decision` agora refletem o resultado real:

| Decision | `.decision` (DB) | `.status` (DB) |
|---|---|---|
| ENTRAR | `ENTRAR` | `CONFIRMED` |
| ESPERAR | `ESPERAR` | `FORMATION` |
| REPROVAR | `REPROVAR` | `INVALIDATED` (+ `invalidated_at` preenchido) |

**Decisão de design importante**: a chave natural de uma `Opportunity`
(`asset+timeframe+playbook+direction`) é usada para localizar o registro
a atualizar **independente do status atual** — inclusive um já
`INVALIDATED`. Isso permite que um REPROVAR num ciclo vire ENTRAR num
ciclo seguinte (mercado mudou) sem criar uma linha duplicada, mas também
significa que a tabela `opportunities` **não distingue ocorrências
históricas separadas** do mesmo playbook no mesmo ativo/timeframe/direção
(ex.: duas Springs em datas diferentes colapsam no mesmo registro). Isso
é aceitável para o estado atual do sistema, mas quem for implementar a
Fase 11 (Future Opportunity Engine) ou a Fase 12 (Analytics/histórico)
vai precisar de uma chave mais fina — provavelmente incluindo o
timestamp do evento estrutural que originou o sinal.

## Worker 24/7 completo (Fase 8 — implementado)

Fecha duas lacunas deixadas pela Fase 7:

1. **Regime HTF real** — `playbooks/runner.py::compute_htf_regime` calcula
   o regime de estrutura num timeframe maior (mapeamento
   `HTF_TIMEFRAME_MAP`: `15m/1h -> 4h`, `4h -> 1d`, `1d -> None`), mais
   leve que `scan_symbol` (só o necessário para `current_regime`, sem
   indicadores/liquidez/playbooks). `worker/app/main.py::run_scan_cycle`
   cacheia o resultado por HTF distinto **uma vez por ativo por ciclo**
   (não recalcula por combinação asset×timeframe menor) e passa para
   `scan_and_score(..., htf_regime=...)`. Com isso, `confidence` finalmente
   consegue chegar a `"ALTA"` em produção, e o Decision Engine (Fase 7)
   finalmente consegue retornar `ENTRAR` de verdade — testado
   explicitamente (`test_entrar_is_reachable_end_to_end_when_htf_regime_is_available`).
2. **Lock distribuído** (seção 47) — `services/lock_service.py` usa
   `pg_try_advisory_lock`/`pg_advisory_unlock` nativos do Postgres (sem
   Redis) por chave `scan:{symbol}:{timeframe}`. `run_scan_cycle` tenta
   adquirir o lock antes de processar cada par e libera no `finally`;
   se outro processo já o detém, o par é pulado (`scan skip`) sem contar
   como erro — importante assim que houver mais de uma instância do
   Worker rodando (ex.: deploy com múltiplas réplicas no Render).
   Testado com duas conexões de banco reais concorrentes.

## Telegram (Fase 9 — implementado)

`shared/alphaquant_core/telegram/` e `engines/alert_engine.py`:

- **Alert Engine** (`engines/alert_engine.py::decide_alert`, seções
  19-20) — decide SE um evento gera alerta, consultando o histórico real
  da própria tabela `alerts` (não precisa de Redis para dedup/cooldown
  nesta escala):
  - `REPROVAR` sem nunca ter sido alertada antes -> nada (seção 69:
    "nenhuma oportunidade de qualidade" não vira mensagem de invalidação
    de algo que nunca foi anunciado).
  - `ENTRAR` pela primeira vez (ou após não ter sido `SIGNAL` antes) ->
    `SIGNAL`.
  - `ESPERAR` pela primeira vez -> `FUTURE`.
  - `REPROVAR` depois de já ter sido `SIGNAL` ou `FUTURE` -> `INVALIDATION`.
  - Qualquer repetição do mesmo evento dentro do cooldown de 30 min
    (`COOLDOWN`) -> nada, mesmo que o texto interno mude ligeiramente.
- **Formatação** (`telegram/formatting.py`) — os três templates das
  seções 16-18 (`format_signal_message`, `format_future_message`,
  `format_invalidation_message`), preenchidos exclusivamente com dados já
  persistidos (`Opportunity.audit_snapshot`: `conditions_met`, `targets`,
  motivos do Quality Filter/Decision Engine) — nunca um valor de exemplo
  do documento original.
- **Cliente** (`telegram/client.py::TelegramClient`) — wrapper fino sobre
  `python-telegram-bot`; em `TEST_MODE=true` (padrão), prefixa toda
  mensagem com `🧪 TEST MODE` (seção 52), aplicado num único lugar para
  que nada no resto do sistema possa esquecer disso.
- **Fila** (`telegram/queue.py`, seções 43-44) — a própria tabela
  `alerts` É a fila: `enqueue_alert` grava `PENDING`;
  `process_pending_alerts` (chamado uma vez por ciclo, em lote, no fim de
  `run_scan_cycle`) processa cada `PENDING`, chama a API real e atualiza
  `telegram_status`/`message_id`/`sent_at` (sucesso) ou
  `retry_count`/`error` (falha). Até 3 tentativas; na 3ª falha vira
  `FAILED` definitivo e nunca mais é reprocessado. Uma mensagem já `SENT`
  nunca é reenviada.

**Escopo explicitamente adiado**: o resumo diário (seção 21) e o
relatório semanal (seção 22) exigem agregação sobre a atividade do
scanner ao longo do dia/semana — isso se encaixa melhor na Fase 12
(Analytics), que já vai ter os endpoints agregados na API. Implementá-los
agora seria antecipar trabalho que depende de dados que a Fase 12 ainda
vai desenhar.

## Engines — status final

Cada Engine tem responsabilidade própria — nenhum substitui outro. Todos
implementados e testados (Fases 3-9):

- **Data Engine** — ✅ Fase 3.
- **Structure Engine** — ✅ Fase 3.
- **Liquidity Engine** — ✅ Fase 4.
- **Smart Money Engine** (Order Blocks/FVG) — ✅ Fase 4.
- **Playbook Engine** — ✅ Fase 4.
- **Volume Engine** — `volume_avg20`/`volume_last` em `indicators.py`,
  usado pelos playbooks que precisam de confirmação de volume
  (Compression Breakout, Open Range Breakout).
- **Wyckoff** — spring/upthrust ✅ implementados como playbooks (Fase 4).
- **Evidence Engine** — `conditions_met`/`conditions_missing` de cada
  `PlaybookResult`, persistido na tabela `evidence` desde a Fase 5.
- **Targets Engine** — ✅ Fase 5.
- **Scoring Engine** — ✅ Fase 5.
- **Quality Filter** — ✅ Fase 6.
- **Decision Engine** — ✅ Fase 7.
- **Alert Engine** — ✅ Fase 9 (dedup + cooldown de 30 min).
- **Future Opportunity Engine** — ✅ Fase 11 (ver seção própria abaixo).
- **Backtest Engine** — ✅ Fase 13 (ver seção própria abaixo).

Ordem de execução por ciclo (nunca invertida — seção 68):

```
DATA -> CONTEXT -> REGIME -> HTF -> MTF -> LTF -> LIQUIDITY -> VOLUME ->
SMART MONEY -> WYCKOFF -> PLAYBOOK -> ENTRY -> STOP -> TARGETS -> RR ->
EXPECTANCY -> SCORE -> QUALITY FILTER -> DECISION ENGINE -> TELEGRAM
```

## Webhook do TradingView

`POST /webhooks/tradingview` autentica por HMAC-SHA256 (header
`X-Signature`, segredo em `TRADINGVIEW_WEBHOOK_SECRET`), valida timestamp
contra replay (janela de 60s) e apenas grava um `ScannerEvent` — nenhum
processamento pesado roda dentro da requisição HTTP. O Worker consome os
eventos no próximo ciclo.

## Dashboard (Fase 10 — implementado)

**API** — três routers novos além dos existentes desde a Fase 3
(`health`, `webhooks`, `market_data`):

- `routers/opportunities.py` — `GET /opportunities` (lista, filtros por
  `status`/`playbook`/`asset`) e `GET /opportunities/{id}` (detalhe
  completo, incluindo `audit_snapshot` e todas as linhas de `evidence`).
- `routers/playbooks.py` — `GET /playbooks` (os 10 playbooks e seus
  limiares).
- `routers/summary.py` — `GET /summary` (contadores das últimas 24h —
  reaproveitado pela Fase 12 como base do resumo diário).
- `routers/backtests.py` (Fase 13) — `GET /backtests`.

**Frontend** (`frontend/`, Next.js 14 App Router + TypeScript +
Tailwind, dark institutional trading terminal per seção 60) — 5 páginas:

| Rota | Conteúdo | Seção da spec |
|---|---|---|
| `/` | Cards de resumo (analisadas, Score≥70/80/90, confirmadas, etc.) | 31 |
| `/scanner` | Tabela de oportunidades ao vivo | 32 |
| `/opportunities/[id]` | Detalhe + Evidence Panel completo | 34, 36 |
| `/playbooks` | Status/limiares dos 10 playbooks | 58-59 |
| `/health` | System Health por serviço | 37 |

`lib/api.ts` é o único ponto de contato com a API (nunca acessa o banco
diretamente); os tipos TypeScript espelham exatamente os dicts que os
routers da API devolvem. Validado com `npm run build` (compilação +
type-check das 5 rotas, sem erros).

**Pendência de produção**: `npm audit` reporta CVEs conhecidas mesmo na
última versão patch da linha Next.js 14.x (14.2.35) — a correção completa
exige migrar para o Next 16 (major version, fora do escopo desta
entrega). Ver `frontend/README.md`.

## Future Opportunity Engine (Fase 11 — implementado)

Todo `PlaybookResult` com `matched=False` mas `direction` definida e
`progress>0` agora vira uma `Opportunity` de verdade
(`services/opportunity_service.py::upsert_future_opportunity`):
`status=FORMATION`, `decision=None` (nunca passa pelo Quality
Filter/Decision Engine — esses são exclusivos de playbooks confirmados),
sem `entry`/`stop`/`rr` (ainda não existem). `playbooks/runner.py::
scan_and_score` decide automaticamente qual caminho seguir por
`PlaybookResult`: `matched=True` vai pelo pipeline completo (Fases 5-7);
`matched=False` com `progress>0` vai pelo caminho "future".

Duas regras de proteção importantes:

- **Nunca sobrescreve** uma `Opportunity` já `CONFIRMED`/`INVALIDATED`
  por um ciclo completo anterior — só `upsert_opportunity` (pipeline
  completo) pode mexer nessas. Evita que uma leitura parcial "rebaixe"
  por engano um sinal que já virou ENTRAR/REPROVAR de verdade.
- **Invalidação automática** (seção 18): se `progress` volta a `0` para
  um setup que estava em `FORMATION`, a `Opportunity` é movida para
  `INVALIDATED` (com `invalidated_at` e motivo registrados) em vez de
  ficar parada para sempre.

**Limitação conhecida, aceita por ora**: se a direção do viés mudar entre
ciclos (o mesmo playbook passa a apontar SHORT em vez de LONG), a
Opportunity antiga do lado oposto não é localizada (a direção é parte da
chave de busca) e fica órfã em `FORMATION` — cenário raro.

## Analytics (Fase 12 — implementado)

`telegram/summary.py`: `compute_daily_summary`/`format_daily_summary_message`
(seção 21) e `compute_weekly_report`/`format_weekly_report_message`
(seção 22), calculados **exclusivamente** a partir de `opportunities` já
persistidas — nenhuma métrica de P&L real (profit factor de trades
executados, expectância real) é fabricada, já que o sistema não executa
ordens. O relatório semanal declara isso explicitamente na própria
mensagem. `risk_status` no resumo diário é uma heurística simples e
honesta (taxa de reprovação do dia), não gestão de risco de posição real.

Entrypoints de cron: `worker/app/cron_daily_summary.py` e
`worker/app/cron_weekly_report.py`, agendados via Render Cron Jobs
(`render.yaml`).

## Backtest Engine (Fase 13 — implementado)

`engines/backtest.py` — reavalia um Playbook **candle a candle** sobre o
histórico já coletado (tabela `candles`), usando em cada ponto só a
janela `[i-lookback, i]` (sem lookahead bias). Quando um sinal aparece,
simula forward até o preço bater o stop ou o TP1, classificando o trade
como `WIN`/`LOSS`/`TIMEOUT` (timeout é excluído das estatísticas — nunca
fabrica um resultado desconhecido). `compute_backtest_stats` calcula
win rate, payoff, profit factor, expectância e max drawdown a partir só
dos trades decididos.

`playbooks/backtest_runner.py::run_and_save_backtest` carrega os candles
direto do banco (`load_candles_df`, reaproveita o histórico que o Worker
já vem coletando organicamente) e persiste em `backtests`
(`services/backtest_service.py`). Entrypoint de cron:
`worker/app/cron_backtest.py` (semanal), roda os 10 playbooks contra
todo `asset`/`timeframe` de `SCAN_ASSETS`/`SCAN_TIMEFRAMES` com histórico
suficiente. Endpoint `GET /backtests` expõe os resultados.

**Nenhum playbook deve virar `ACTIVE`** na tabela `playbooks` sem
resultados de backtest consistentes (seção 55) — isso continua sendo uma
decisão manual (trocar o `status` direto no banco), não automatizada.

## Production Hardening (Fase 14 — implementado)

- **Retry com backoff exponencial** (`services/retry.py::retry_with_backoff`,
  seção 39 — self-healing) — aplicado em `BinanceMarketDataClient._get`:
  erros transientes (timeout, conexão, HTTP 429/500/502/503/504) tentam
  de novo (até 3x, backoff `0.5s, 1s, 2s...`); erros do cliente (400,
  404 — símbolo inválido) falham imediatamente, já que retry não mudaria
  o resultado.
- **Rate limiting** (`services/rate_limiter.py::RateLimiter`, seção 42)
  — espaçamento mínimo entre chamadas consecutivas, aplicado tanto no
  cliente Binance (0.25s) quanto no `TelegramClient` (1s). Suficiente
  para a escala atual (um único Worker); não é um token bucket
  distribuído.

**Itens do checklist de produção ainda pendentes de execução manual**
(não são código, são passos operacionais — ver `docs/DEPLOY.md`):
domínio configurado, Telegram Bot criado e testado, `TEST_MODE=false`
só depois de confirmar os critérios da seção 53, `npm audit fix` no
frontend antes de expor publicamente.

## Banco de dados

Schema completo já criado em `shared/alphaquant_core/db/models.py`:
`assets`, `candles`, `opportunities`, `evidence`, `playbooks`, `alerts`,
`scanner_events`, `system_health`, `backtests` — exatamente conforme a
seção 11 do master prompt.

## Roadmap de fases

| Fase | Escopo | Status |
|---|---|---|
| 1 | Arquitetura, estrutura de pastas, schema do banco, esqueleto API + Worker | ✅ feito |
| 2 | Migrations (Alembic) — `api/migrations`, revisão `0001_initial_schema` | ✅ feito |
| 3 | Market Data Engine — cliente Binance público, indicadores (EMA/RSI/ATR/MACD), Structure Engine (swings/HH-HL-LH-LL/BOS/CHOCH), persistência de candles | ✅ feito |
| 4 | Playbook Engine (10 playbooks) | ✅ feito |
| 5 | Scoring Engine — Targets Engine (TP1-3/RR), Score auditável (Contexto/Estrutura/Execução/bônus), persistência de `Opportunity`+`evidence` | ✅ feito |
| 6 | Quality Filter — bloqueios absolutos (seção 27), limiares por playbook lidos da tabela `playbooks` | ✅ feito |
| 7 | Decision Engine — ENTRAR/ESPERAR/REPROVAR, pipeline da seção 68 fechado ponta a ponta | ✅ feito |
| 8 | Worker 24/7 completo — regime HTF real (fecha a lacuna da Fase 7) + lock distribuído (`pg_advisory_lock`) | ✅ feito |
| 9 | Telegram (bot, fila, dedup, cooldown) — resumo diário/semanal adiado para a Fase 12 (Analytics) | ✅ feito |
| 10 | Dashboard (Next.js/Vercel) — API estendida (opportunities, playbooks, summary, backtests) + frontend com 5 páginas | ✅ feito |
| 11 | Future Opportunity Engine — playbooks parciais viram Opportunity FORMATION sem Decision Engine, com invalidação automática | ✅ feito |
| 12 | Analytics — resumo diário e relatório semanal via Telegram, cron jobs | ✅ feito |
| 13 | Backtest — replay histórico real sem lookahead bias, persistido em `backtests` | ✅ feito |
| 14 | Production hardening — retry com backoff exponencial + rate limiting (Binance e Telegram) | ✅ feito |
