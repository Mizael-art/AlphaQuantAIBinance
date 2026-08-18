# ALPHAQUANT X

### MARKET INTELLIGENCE & TRADE SCANNER — 24/7

> **DON'T CHASE TRADES. FIND QUALITY.**
> NÃO PERSIGA TRADES. ENCONTRE QUALIDADE.

Trading Intelligence Operating System composto por API (FastAPI),
Worker 24/7 (scanner), PostgreSQL, bot do Telegram e Dashboard
(Next.js). Monitora múltiplos timeframes contra 10 Playbooks oficiais,
calcula Score/RR/Confiança, aplica Quality Filter e Decision Engine, e
só alerta quando há evidência de alta qualidade — nunca fabrica sinais.

Veja `docs/ARCHITECTURE.md` para o desenho técnico completo,
`docs/PROJECT_PLAN.md` para o histórico de decisões fase a fase, e
`docs/DEPLOY.md` para o passo a passo de deploy (Vercel + Render).

## Estrutura

```
alphaquant-x/
├── api/                      # FastAPI — dashboard backend + webhook TradingView
│   ├── app/
│   │   ├── main.py
│   │   └── routers/          # health, webhooks, market_data, opportunities,
│   │                         # playbooks, summary, backtests
│   ├── migrations/            # Alembic — 0001 schema, 0002 seed dos playbooks
│   └── tests/                  # testes dos endpoints (Postgres real via pgserver)
├── worker/                    # Scanner 24/7 (Render Background Worker)
│   ├── app/
│   │   ├── main.py             # loop + heartbeat + pipeline completo (Fases 3-9)
│   │   ├── cron_daily_summary.py   # Fase 12 — Render Cron Job diário
│   │   ├── cron_weekly_report.py   # Fase 12 — Render Cron Job semanal
│   │   └── cron_backtest.py         # Fase 13 — Render Cron Job semanal
│   └── tests/                        # 127 testes (unitários + integração c/ Postgres real)
├── frontend/                  # Dashboard (Next.js 14 App Router + TypeScript + Tailwind)
│   ├── app/                    # /, /scanner, /opportunities/[id], /playbooks, /health
│   └── lib/api.ts               # único ponto de contato com a API
├── shared/alphaquant_core/     # schema, config e engines usados por api e worker
│   ├── core/config.py
│   ├── db/                      # models.py (schema), session.py
│   ├── engines/                  # data_engine, indicators, structure, liquidity,
│   │                             # targets, scoring, quality_filter, decision,
│   │                             # alert_engine, backtest
│   ├── services/                  # candle_service, opportunity_service, lock_service,
│   │                               # backtest_service, retry, rate_limiter
│   ├── playbooks/                  # base, os 10 playbooks, engine.py, runner.py,
│   │                               # backtest_runner.py
│   └── telegram/                    # client.py, formatting.py, queue.py, summary.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOY.md
│   └── PROJECT_PLAN.md            # plano de execução completo (Fases 1-14) — handoff
├── render.yaml                     # API + Worker + 3 Cron Jobs + Postgres
└── .env.example
```

## Rodando localmente

```bash
# shared + api
cd api && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # preencher com valores reais
alembic upgrade head          # aplica schema + seed dos 10 playbooks
uvicorn app.main:app --reload

# worker (em outro terminal)
cd worker && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app/main.py

# frontend (em outro terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## Testes

```bash
cd worker && pip install -r requirements.txt && pytest tests/ -v   # 127 testes
cd api && pip install -r requirements.txt && pytest tests/ -v       # 8 testes
cd frontend && npm install && npm run build                          # build + type-check
```

Os testes de integração (worker e api) sobem um PostgreSQL real e
efêmero automaticamente via `pgserver` (pacote pip puro, sem
apt/docker) — nenhum banco externo é necessário para rodar a suíte
localmente ou em CI.

## Status — Fases 1-14 concluídas

O núcleo completo do master prompt está implementado e testado contra
Postgres real (nunca só mocks). Resumo por fase — detalhes de cada uma,
decisões de design e bugs reais encontrados/corrigidos ao testar estão
em `docs/PROJECT_PLAN.md`, seção 3.

| Fase | Entrega |
|---|---|
| 1 | Arquitetura, schema completo (9 tabelas), scaffold API + Worker |
| 2 | Migrations Alembic (schema + seed dos 10 playbooks) |
| 3 | Data Engine — Binance público, indicadores, Structure Engine |
| 4 | Playbook Engine — os 10 playbooks oficiais |
| 5 | Scoring Engine — Targets/RR, Score auditável, persistência |
| 6 | Quality Filter — bloqueios absolutos por playbook |
| 7 | Decision Engine — ENTRAR/ESPERAR/REPROVAR, pipeline fechado |
| 8 | Worker 24/7 completo — regime HTF real + lock distribuído |
| 9 | Telegram — Alert Engine, formatação, cliente, fila com retry |
| 10 | Dashboard — API estendida + frontend Next.js (5 páginas) |
| 11 | Future Opportunity Engine — setups em formação + invalidação automática |
| 12 | Analytics — resumo diário/semanal via Telegram (cron) |
| 13 | Backtest Engine — replay histórico sem lookahead, persistido |
| 14 | Production hardening — retry com backoff + rate limiting |

**Números**: 127 testes no worker + 8 na API (135 no total), todos
passando contra PostgreSQL real. 10 playbooks, 9 tabelas, ~15 engines,
3 cron jobs, 5 páginas de dashboard.

**Pendências operacionais antes de produção real** (não são código —
são passos manuais, ver `docs/DEPLOY.md` e `docs/PROJECT_PLAN.md` seção
5): criar o Bot do Telegram, configurar domínio, confirmar os critérios
da seção 53 antes de `TEST_MODE=false`, e rodar `npm audit fix` no
frontend (CVEs conhecidas do Next.js 14.x — corrigidas só migrando para
o Next 16, fora do escopo desta entrega).
