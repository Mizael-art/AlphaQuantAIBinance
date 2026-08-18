# PROJECT_PLAN.md — ALPHAQUANT X

### Documento de handoff — como o projeto foi construído (projeto completo, Fases 1-14)

Este documento existe para que qualquer programador consiga assumir o
projeto sem depender de contexto que só existe nesta conversa. As 14
fases do master prompt estão implementadas e testadas — este documento
cobre (1) as decisões de arquitetura tomadas e por quê, (2) o que foi
implementado e testado em cada fase, com os bugs reais encontrados e
como foram corrigidos, e (3) o que fica como trabalho de evolução
natural a partir daqui (seção 4 — não são mais "fases pendentes", já que
não há nenhuma).

A especificação completa e original do projeto está em
`docs/ARCHITECTURE.md` (arquitetura técnica) e no master prompt que deu
origem a este repositório — este documento aqui é o **plano de execução**,
não substitui a especificação.

---

## 1. Visão geral do que está sendo construído

AlphaQuant X é um **Trading Intelligence Operating System**, não um site:
um Worker 24/7 monitora continuamente ativos cripto contra 10 Playbooks
técnicos, calcula um Score de qualidade da evidência (não de
probabilidade de lucro), aplica um Quality Filter com bloqueios
absolutos, decide ENTRAR / ESPERAR / REPROVAR e só então alerta via
Telegram. Quando não há oportunidade de qualidade, isso é reportado como
resultado válido — o sistema nunca fabrica sinais.

Regra de ouro que atravessa todas as fases: **nenhuma camada inventa
dado**. Falha de rede vira `BinanceRequestError` e é registrada, nunca
mascarada. Ausência de setup vira "NO HIGH-QUALITY OPPORTUNITY", nunca um
sinal fraco disfarçado.

---

## 2. Decisões de arquitetura (por quê, não só o quê)

### 2.1 Dois serviços (API + Worker), nunca um monólito

- **API** (`api/`, FastAPI, Render Web Service): serve o dashboard
  (Fase 10), recebe o webhook do TradingView, expõe `/health` e um
  endpoint de debug `/market-data/{symbol}`.
- **Worker** (`worker/`, Render Background Worker): processo de loop
  infinito, roda o scanner 24/7. **Nunca** depende do navegador estar
  aberto — essa é uma restrição explícita da especificação original
  (seção 9 do master prompt).

### 2.2 Pacote compartilhado `shared/alphaquant_core`

API e Worker leem/escrevem o mesmo banco e precisam das mesmas engines
(ex.: a API expõe `/market-data` chamando a mesma lógica que o Worker usa
no scanner). Em vez de duplicar código entre os dois serviços, tudo que é
compartilhado vive em `shared/alphaquant_core`, instalado como pacote
Python local editável (`-e ../shared` no `requirements.txt` de cada
serviço). Isso é montado via `pyproject.toml` próprio em `shared/`.

**Convenção**: qualquer engine, model ou service usado por mais de um
serviço vai em `shared/alphaquant_core/`. Código específico de orquestração
do loop do Worker (ex.: `worker/app/main.py`) ou de rotas HTTP
(`api/app/routers/`) fica no serviço correspondente.

```
shared/alphaquant_core/
├── core/config.py       # Settings (pydantic-settings), única fonte de env vars
├── db/
│   ├── models.py        # schema SQLAlchemy — fonte única de verdade do banco
│   └── session.py       # engine + SessionLocal + Base
├── engines/
│   ├── data_engine.py    # cliente Binance público (Fase 3)
│   ├── indicators.py     # EMA/RSI/ATR/MACD/atr_contraction_ratio (Fase 3-4)
│   ├── structure.py      # swings, HH/HL/LH/LL, BOS/CHOCH (Fase 3)
│   ├── liquidity.py      # FVG, Order Blocks, Liquidity Sweep (Fase 4)
│   └── orchestrator.py   # fetch_and_persist() + analyze_asset() (Fase 3)
├── services/
│   └── candle_service.py # upsert idempotente de candles (Fase 3)
├── playbooks/              # os 10 Playbooks (Fase 4 — completo)
│   ├── base.py              # PlaybookContext, PlaybookResult, Playbook
│   ├── <um arquivo por playbook>
│   ├── engine.py             # build_context() + evaluate_all()
│   └── runner.py             # scan_symbol() — integra com o Data Engine
```

### 2.3 Banco de dados: schema fixo desde a Fase 1, migrations desde a Fase 2

O schema completo (9 tabelas: `assets`, `candles`, `opportunities`,
`evidence`, `playbooks`, `alerts`, `scanner_events`, `system_health`,
`backtests`) foi definido **inteiro** já na Fase 1, mesmo com a maioria
das tabelas ainda não sendo escrita por nenhum código (`evidence`,
`alerts`, `backtests` só passam a ser usadas nas Fases 5+, 9 e 13). Isso
foi proposital: qualquer alteração de schema depois disso é uma migration
incremental (Alembic), nunca uma reescrita.

**Convenção**: mudou `models.py`? Sempre gerar uma nova revisão Alembic
(`alembic revision -m "..."`) na mesma tarefa — nunca deixar o ORM e as
migrations divergirem.

### 2.4 Metodologia de teste: sempre contra Postgres real, nunca só mocks

Cada fase só foi considerada concluída depois de rodar contra um
PostgreSQL real — usando o pacote `pgserver` (Postgres embarcado via pip,
sem exigir Docker/apt), o que permite testes de integração 100% reais
(`ON CONFLICT`, ENUMs nativos, etc.) rodando em qualquer ambiente,
inclusive CI. Ver `worker/tests/conftest.py`: ele sobe um Postgres efêmero
*antes* de qualquer import do pacote `alphaquant_core`, roda os testes, e
derruba o banco no fim.

**Convenção para as próximas fases**: todo novo código que toca o banco
precisa de teste de integração usando a fixture `db_session` já pronta em
`conftest.py`. Lógica pura (cálculo de score, regras de playbook) leva
teste unitário sem banco.

### 2.5 Nunca fabricar dado em caso de erro

`BinanceRequestError` existe para que uma falha de rede vire um evento
registrado (`scanner_events`) e um estado `DEGRADED` em `system_health` —
nunca um valor inventado passando adiante no pipeline. Essa mesma postura
deve se repetir em toda fase futura: se o Telegram falhar (Fase 9), vira
retry + log, nunca "finge que enviou". Se o Score não puder ser calculado
por falta de dado (Fase 5), o Playbook correspondente deve reportar
`matched=False` com a condição faltante explícita, nunca um score parcial
disfarçado de final.

---

## 3. O que já está pronto (Fases 1–14) — projeto completo, testado de ponta a ponta

| Fase | Entregável | Como foi validado |
|---|---|---|
| 1 | Estrutura de pastas, schema completo do banco, esqueleto FastAPI (`/`, `/health`) e Worker (loop + heartbeat), `render.yaml`, `.env.example` | `Base.metadata.create_all()` cria as 9 tabelas sem erro; `TestClient` bate em `/` e `/health` |
| 2 | Migration inicial (`api/migrations/versions/0001_initial_schema.py`) com as 9 tabelas + 6 ENUMs nativos do Postgres | `alembic upgrade head` → `downgrade base` → `upgrade head` novamente, contra Postgres real, sem sobras |
| 3 | Data Engine: `BinanceMarketDataClient` (klines/ticker/depth públicos), indicadores (EMA20/50/100/200, RSI14, ATR14, MACD, volume médio), Structure Engine (swings, HH/HL/LH/LL, BOS/CHOCH), persistência idempotente de candles, endpoint `GET /market-data/{symbol}` | 17 testes automatizados, incluindo integração contra Postgres real; idempotência confirmada; erro de rede tratado corretamente |
| 4 | Playbook Engine: Liquidity/Smart Money Engine de apoio (FVG, Order Blocks, Liquidity Sweep), `atr_contraction_ratio` (detecção de squeeze), os 10 Playbooks oficiais, `playbooks/engine.py` (monta contexto + roda todos), `playbooks/runner.py` (integra com o Data Engine sem buscar candles duas vezes), migration `0002_seed_playbooks.py`, integração completa no loop do Worker | 21 testes com fixtures sintéticas desenhadas (iterativamente, contra a implementação real) para acionar cada padrão especificamente; migration de seed testada `upgrade`/`downgrade`/`upgrade` contra Postgres real; `run_scan_cycle` testado de ponta a ponta (Data Engine → Playbook Engine → persistência) tanto com falha de rede real (tratada sem derrubar o worker) quanto com dados sintéticos que efetivamente acionam playbooks |
| 5 | Scoring Engine: `engines/targets.py` (TP1-3/RR com alvos estruturais reais, filtro de ruído `MIN_RR_FOR_STRUCTURAL_TARGET`, fallback em múltiplos de R), `engines/scoring.py` (Score auditável Contexto/Estrutura/Execução/bônus, sempre ≤100), `services/opportunity_service.py` (upsert de `Opportunity`+`evidence`, `compute_confidence` independente de Score/Progress), `playbooks/runner.py::scan_and_score` (só persiste playbooks confirmados; status sempre `FORMATION`) | 19 testes novos (7 de targets, 8 de scoring, 4 de integração de persistência contra Postgres real); `run_scan_cycle` completo testado de ponta a ponta incluindo dois bugs reais encontrados e corrigidos ao testar (ver seção 3, notas de design) |
| 6 | Quality Filter: `engines/quality_filter.py` (`evaluate_quality` — todos os bloqueios absolutos da seção 27, reportados juntos, nunca só o primeiro), limiares `minimum_score`/`minimum_rr` lidos por playbook da tabela `playbooks` (`_playbook_thresholds` em `runner.py`, não fixos no código), veredito gravado em `audit_snapshot["quality_filter"]` e como linha própria de `evidence` (`category="QUALITY_FILTER"`) | 8 testes unitários (um por bloqueio + combinação + limiar por playbook) + 1 teste de integração confirmando o veredito persistido com os limiares reais da tabela; testado de ponta a ponta contra Postgres real via migration — no mesmo ciclo, um playbook foi corretamente REPROVADO (RR e Score abaixo do mínimo) e outro APROVADO |
| 7 | Decision Engine: `engines/decision.py` (`make_decision` — REPROVAR se Quality Filter reprovou, ENTRAR se aprovado+confidence ALTA, ESPERAR se aprovado mas confidence não-ALTA), `Opportunity.status`/`.decision` finalmente reais (CONFIRMED/FORMATION/INVALIDADO + `invalidated_at`), `upsert_opportunity` reescrito para localizar o registro por asset+timeframe+playbook+direction **independente do status** (permite REPROVAR→ENTRAR num ciclo seguinte sem duplicar) | 5 testes unitários do Decision Engine + 3 testes de integração novos (consistência Quality Filter↔Decision, não-duplicação ao reavaliar); pipeline completo (Fases 3-7) testado contra Postgres real via migration de produção — no mesmo ciclo, um playbook virou REPROVAR/INVALIDATED e outro ESPERAR/FORMATION, cada um com motivo exato registrado |
| 8 | Worker 24/7 completo: `playbooks/runner.py::compute_htf_regime` + `HTF_TIMEFRAME_MAP` (regime HTF real, cacheado por ativo por ciclo — fecha a lacuna da Fase 7 que impedia `ENTRAR`), `services/lock_service.py` (`pg_try_advisory_lock`/`pg_advisory_unlock`, sem Redis), `run_scan_cycle` reescrito para adquirir/liberar lock por `asset+timeframe` e pular (não como erro) quando outro processo já o detém | 7 testes novos (3 de lock com conexões concorrentes reais, 4 de HTF regime) + 1 teste de integração que prova `ENTRAR` sendo alcançado de ponta a ponta com HTF disponível; testado contra Postgres real via migration incluindo o cenário de lock ocupado por um segundo processo simulado |
| 9 | Telegram: `engines/alert_engine.py` (`decide_alert` — dedup/cooldown de 30min usando a própria tabela `alerts` como histórico), `telegram/formatting.py` (os 3 templates das seções 16-18, preenchidos só com dados reais persistidos), `telegram/client.py` (`TelegramClient`, `TEST_MODE`-aware), `telegram/queue.py` (`enqueue_alert`/`process_pending_alerts` — a tabela `alerts` É a fila, retry até 3 tentativas), tudo integrado ao `run_scan_cycle` (enfileira por Opportunity, processa a fila uma vez por ciclo em lote) | 7 testes de formatação + 7 de integração (SIGNAL/FUTURE/INVALIDATION, cooldown real com timestamps manipulados, retry até FAILED em 3 tentativas confirmado, nunca reenvia um SENT); resumo diário/semanal (seções 21-22) explicitamente adiado para a Fase 12 (Analytics) — depende de agregação que ainda não existe |
| 10 | Dashboard: 3 routers novos na API (`opportunities.py` — lista+detalhe com evidence, `playbooks.py`, `summary.py`), frontend Next.js 14 App Router + TypeScript + Tailwind (5 páginas: `/`, `/scanner`, `/opportunities/[id]`, `/playbooks`, `/health`), `lib/api.ts` como único ponto de contato com a API | Endpoints testados contra Postgres real com dados gerados pelo pipeline completo; `npm run build` validado (compilação + type-check das 5 rotas sem erro); contrato TypeScript↔API conferido por revisão de código (mesma fonte de verdade) |
| 11 | Future Opportunity Engine: `services/opportunity_service.py::upsert_future_opportunity` (playbooks `matched=False` com direção e progresso viram `Opportunity` `FORMATION`/`decision=None`, nunca passam pelo Quality Filter/Decision Engine), invalidação automática quando `progress` volta a 0, proteção contra sobrescrever uma Opportunity já `CONFIRMED`/`INVALIDATED` | 6 testes de integração (persistência, sem direção não persiste, nunca sobrescreve confirmado/invalidado, reaproveita a mesma linha entre ciclos, invalidação automática, mensagem Telegram renderiza corretamente para um setup invalidado); Alert Engine atualizado para emitir `FUTURE` também para `decision=None` |
| 12 | Analytics: `telegram/summary.py` (`compute_daily_summary`/`compute_weekly_report` + formatadores, seções 21-22), só com dados reais já persistidos (nunca fabrica P&L de trades que o sistema não executa), entrypoints de cron `worker/app/cron_daily_summary.py`/`cron_weekly_report.py` | 6 testes (resumo/relatório vazios bem formados, refletem dados reais, heurística de risk_status, nunca fabrica métricas de P&L); bug real corrigido: agregações usavam só `>= since` sem limite superior `<= now`, quebrando isolamento entre testes — corrigido com `.between(since, now)` em todas as 10 ocorrências |
| 13 | Backtest Engine: `engines/backtest.py` (`run_backtest`/`compute_backtest_stats` — replay candle a candle sem lookahead bias, simulação forward até stop/TP1, timeout excluído das estatísticas), `services/backtest_service.py` + `playbooks/backtest_runner.py` (`load_candles_df`/`run_and_save_backtest`, reaproveita candles já persistidos pelo Data Engine), endpoint `GET /backtests`, entrypoint `worker/app/cron_backtest.py` | Matemática de win_rate/payoff/profit_factor/expectancy/max_drawdown validada manualmente com trades de resultado conhecido; 6 testes unitários + 4 de integração (persistência contra Postgres real); mesmo bug de `numpy.float64` das Fases 4-5 reapareceu numa `Candle` construída sem `float()` — corrigido também defensivamente em `candle_service.upsert_candles` |
| 14 | Production hardening: `services/retry.py` (`retry_with_backoff` — backoff exponencial, seção 39) e `services/rate_limiter.py` (`RateLimiter` — espaçamento mínimo, seção 42), aplicados em `BinanceMarketDataClient` (retry em erros transientes/429/5xx, falha imediata em 400/404) e `TelegramClient` | 7 testes novos (4 de retry, 3 de rate limiter, com clock/sleep injetáveis para não depender de tempo real); testes de `data_engine.py` recalibrados para não gastar tempo real de espera |

Detalhes técnicos de cada indicador/estrutura/playbook estão documentados
em `docs/ARCHITECTURE.md`.

Duas decisões de design que só ficaram claras testando de verdade (vale
o registro para quem for mexer nessas áreas):

- **`FairValueGap.filled`** não pode significar "uma candle futura tocou o
  gap" — isso marcaria o gap como preenchido no exato momento em que o
  preço retorna a ele, inutilizando o Playbook FVG Retracement (que
  precisa reagir exatamente a esse retorno). A definição correta é
  "o preço fechou do outro lado do gap inteiro" (`close` além da borda
  oposta), não um simples toque.
- **`atr_contraction_ratio`** precisa excluir a candle mais recente do
  cálculo do "ATR atual" (parâmetro `exclude_last=1`, padrão). Do
  contrário, o próprio range grande da candle de rompimento/sweep infla a
  leitura de volatilidade "atual" e mascara a compressão real que a
  precedeu — o que fazia os Playbooks Wyckoff Spring/Upthrust e
  Compression Breakout nunca baterem mesmo em cenários de squeeze óbvio.
- **`numpy.float64` vazando até uma coluna do banco quebra o driver
  psycopg2** com um erro obscuro (`InvalidSchemaName: schema "np" does
  not exist` — psycopg2 cai num fallback que injeta o `repr()` do valor
  como texto SQL cru). Aconteceu porque `detect_fair_value_gaps` (Fase 4)
  guardava `highs[i-2]`/`lows[i]` direto do array numpy sem `float()`.
  Corrigido na origem (`liquidity.py`) e reforçado com uma função
  `_as_float()` em `opportunity_service.py` que converte tudo antes de
  gravar — qualquer engine nova que grave no banco deve fazer o mesmo
  (nunca confiar que o valor já é um `float` nativo só porque "parece"
  um).
- **Um swing estrutural muito próximo da entrada não é um alvo útil** —
  numa faixa lateral, o "próximo swing high" pode estar a menos de 1% de
  distância, o que infla artificialmente o RR calculado ou o torna
  irrisório sem significado prático. `engines/targets.py` só aceita um
  swing como alvo estrutural se a distância for ≥ 1R
  (`MIN_RR_FOR_STRUCTURAL_TARGET`); abaixo disso, cai no fallback de
  múltiplos de R.

**Limitação HISTÓRICA, fechada na Fase 8** (registro do que aconteceu,
para quem só ler o histórico entender a evolução): entre a Fase 7 e a
Fase 8, o Playbook HTF Continuation nunca batia em produção e o Decision
Engine nunca retornava `ENTRAR` (só `ESPERAR`/`REPROVAR`), porque
`htf_regime` sempre chegava `None` — `compute_confidence` só retorna
`"ALTA"` quando `htf_regime` não é `None`. A Fase 8 fechou isso com
`playbooks/runner.py::compute_htf_regime` (calcula o regime num timeframe
maior de verdade, cacheado por ativo por ciclo) — testado explicitamente
provando `ENTRAR` sendo alcançado de ponta a ponta.

**Decisão de design (Fase 7)**: `upsert_opportunity` localiza o registro
a atualizar por `asset+timeframe+playbook+direction`, **sem filtrar por
status** — antes (Fase 5-6) só considerava `FORMATION`/`CONFIRMED`
"abertos", o que faria cada REPROVAR (status `INVALIDATED`) gerar uma
linha nova no ciclo seguinte mesmo que o mesmo playbook continuasse
batendo (crescimento sem controle da tabela). Agora qualquer status é
reaproveitado, o que permite REPROVAR→ENTRAR num ciclo seguinte sem
duplicar, mas tem uma consequência que vale registrar: a tabela
`opportunities` não distingue ocorrências históricas separadas do mesmo
playbook no mesmo ativo/timeframe/direção (duas Springs em datas
diferentes colapsam no mesmo registro, o mais recente sempre sobrescreve
o anterior). Aceitável para o estado atual; a Fase 11 (Future Opportunity
Engine) ou a Fase 12 (Analytics/histórico) provavelmente vão precisar de
uma chave mais fina — incluindo o timestamp do evento estrutural que
originou o sinal — se um histórico completo de ocorrências for exigido.

**Nota de design (Fase 8)**: o lock distribuído (`lock_service.py`) usa
`pg_advisory_lock` nativo do Postgres em vez de introduzir Redis só para
isso — é amarrado à conexão, não à transação, então `try_acquire_lock`/
`release_lock` sempre precisam rodar na mesma `Session` (nunca abrir uma
conexão nova para liberar um lock adquirido em outra). Se uma fase futura
precisar de Redis por outro motivo (fila do Telegram, Fase 9), dá para
migrar o lock também, mas não há necessidade agora.

---

## 4. Projeto completo — não há mais fases em aberto

Todas as 14 fases do master prompt foram implementadas, testadas contra
Postgres real, e estão descritas na seção 3 acima com o que foi de fato
construído, como foi validado, e as decisões de design/bugs reais
encontrados ao testar cada uma. Este documento deixa de ter uma seção de
"plano futuro" — o que resta é trabalho de evolução/manutenção, não
fases pendentes da especificação original.

### O que fica para quem for evoluir o projeto a partir daqui

Nenhum destes itens estava no escopo original — são melhorias naturais
depois que o sistema funciona de ponta a ponta:

- **Promover playbooks de `VALIDATING` para `ACTIVE`** (seção 55): exige
  rodar `cron_backtest.py` com histórico real suficiente (semanas/meses
  de candles) e decidir manualmente, olhando os números de
  `GET /backtests`, se um playbook merece ser promovido. Isso é uma
  decisão de produto, não uma automação — nunca deve ser automática.
- **Tracking de execução real de posições**: hoje o sistema não sabe se
  um `ENTRAR` realmente bateu o TP ou o stop no mundo real — só simula
  isso retroativamente no Backtest (Fase 13). Um módulo de tracking (ex.:
  o usuário confirma manualmente o resultado de cada trade, ou integra
  com uma exchange em modo read-only) destravaria métricas de P&L reais
  no resumo diário/semanal (hoje explicitamente não fabricadas — ver
  Fase 12 na seção 3).
- **Risk Engine completo** (seção 29 da especificação original):
  `risk_per_trade`, `daily_loss_limit`, `weekly_loss_limit`,
  `max_drawdown` configuráveis — hoje o `risk_status` do resumo diário é
  só uma heurística de taxa de reprovação, não gestão de risco de
  posição real.
- **Migração do frontend para Next.js 16**: fecha as CVEs que
  `npm audit` reporta na linha 14.x (ver `frontend/README.md`).
- **Chave mais fina para `Opportunity`** (asset+timeframe+playbook+
  direção+timestamp do evento estrutural): resolveria as duas limitações
  aceitas nas Fases 7 e 11 (troca de direção entre ciclos não localiza a
  Opportunity antiga; ocorrências históricas distintas do mesmo setup
  colapsam no mesmo registro).

---

## 5. Convenções gerais para quem for continuar

- **Nunca** duplicar lógica entre `api/` e `worker/` — se os dois
  precisam, vai em `shared/alphaquant_core/`.
- **Sempre** rodar `pytest tests/ -v` dentro de `worker/` antes de
  considerar uma fase concluída — a suíte sobe Postgres real sozinha via
  `pgserver`, não precisa de infraestrutura externa.
- **Sempre** que `shared/alphaquant_core/db/models.py` mudar, gerar
  migration Alembic no mesmo commit/tarefa.
- Todo módulo de decisão (Playbook, Scoring, Quality Filter, Decision
  Engine) devolve **estruturas explicáveis** (`conditions_met` /
  `conditions_missing`, sub-notas, motivo de reprovação) — nunca só um
  número ou booleano isolado. Isso não é estético: é o que alimenta o
  Evidence Panel (Fase 10) e a Auditoria (seção 57 da especificação —
  "por que o sistema classificou esse trade como 84?" precisa ter
  resposta exata).
- `TEST_MODE=true` é o padrão em todo lugar (`.env.example`, `render.yaml`)
  até a Fase 14 explicitamente autorizar produção real.

---

## 6. Onde encontrar cada coisa

| Preciso de... | Está em... |
|---|---|
| Especificação original completa | master prompt (fora do repositório — conversa com o solicitante) |
| Arquitetura técnica detalhada | `docs/ARCHITECTURE.md` |
| Passo a passo de deploy | `docs/DEPLOY.md` |
| Schema do banco | `shared/alphaquant_core/db/models.py` |
| Histórico de migrations | `api/migrations/versions/` |
| Engines de mercado (Data/Structure/Liquidity/Targets/Scoring/Quality/Decision/Alert/Backtest) | `shared/alphaquant_core/engines/` |
| Serviços de apoio (candle/opportunity/lock/backtest/retry/rate limiter) | `shared/alphaquant_core/services/` |
| Playbooks | `shared/alphaquant_core/playbooks/` |
| Telegram (cliente, formatação, fila, resumos) | `shared/alphaquant_core/telegram/` |
| Loop do Worker | `worker/app/main.py` |
| Entrypoints de cron (resumo diário/semanal, backtest) | `worker/app/cron_*.py` |
| Rotas da API | `api/app/routers/` |
| Dashboard (frontend) | `frontend/app/`, `frontend/lib/api.ts` |
| Testes do worker | `worker/tests/` |
| Testes da API | `api/tests/` |
| Variáveis de ambiente necessárias | `.env.example`, `frontend/.env.local.example` |
| Status resumido do roadmap | `README.md` (seção "Status") |
| Deploy do Worker/API/Cron Jobs | `render.yaml` |
