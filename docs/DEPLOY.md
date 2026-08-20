# DEPLOY.md — ALPHAQUANT X

## Backend (Render)

1. **PostgreSQL** — criar o banco `alphaquantx-db` (região Singapore —
   Oregon é bloqueado pela Binance com HTTP 451, como já visto no
   AlphaQuant Engine). `render.yaml` já declara o recurso.
2. **Migrations (Alembic)** — antes de subir a API/Worker pela primeira
   vez, aplicar o schema:
   ```bash
   cd api
   pip install -r requirements.txt
   alembic upgrade head
   ```
   `migrations/env.py` lê `DATABASE_URL` automaticamente das variáveis de
   ambiente (nunca do `alembic.ini`). O `buildCommand` da API no
   `render.yaml` já roda isso automaticamente a cada deploy.
3. **Worker (Render Background Worker)** — `rootDir: worker`, start
   command `python app/main.py`. Nunca rodar o scanner dentro do
   frontend.
4. **API (Render Web Service)** — `rootDir: api`, start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. **Cron Jobs** (`render.yaml` já declara os três, todos `rootDir: worker`):
   - `alphaquantx-daily-summary` — `python app/cron_daily_summary.py`,
     diário às 23:00 UTC (seção 21).
   - `alphaquantx-weekly-report` — `python app/cron_weekly_report.py`,
     domingo às 23:00 UTC (seção 22).
   - `alphaquantx-backtest` — `python app/cron_backtest.py`, segunda às
     06:00 UTC (seção 55) — só produz resultado útil depois de o Worker
     já ter coletado histórico suficiente de candles (semanas).
6. **Environment Variables** — preencher em cada serviço no painel do
   Render a partir de `.env.example`. Nunca commitar valores reais.
7. **Domínio** — preparar `api.alphaquantx.com`; não assumir que já
   existe.

## Telegram

8. **Criar o Bot** via @BotFather, obter `TELEGRAM_BOT_TOKEN`.
9. **Adicionar o bot** aos grupos/canais de sinais e de oportunidades
   futuras.
10. **Chat ID** — obter os IDs numéricos dos dois canais e preencher
    `TELEGRAM_SIGNALS_CHAT_ID` / `TELEGRAM_FUTURE_CHAT_ID`.
11. **Teste** — com `TEST_MODE=true` (padrão), confirmar que mensagens
    chegam marcadas como `🧪 TEST MODE` e que nenhum alerta é tratado
    como sinal real.
12. **Comando manual `/analisar`** — depois que a API estiver publicada
    (Render já dá a URL `https://<app>.onrender.com`), registrar o
    webhook do Telegram apontando pra ela:
    ```bash
    curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
      -d "url=https://<sua-api>.onrender.com/webhooks/telegram" \
      -d "secret_token=<mesmo valor de TELEGRAM_WEBHOOK_SECRET>"
    ```
    A partir daí, mandar `/analisar` (ou `/scan`) no grupo de sinais
    dispara uma análise imediata, sem esperar o próximo ciclo de
    `SCAN_INTERVAL_MINUTES`. Só chats com `TELEGRAM_SIGNALS_CHAT_ID` ou
    `TELEGRAM_FUTURE_CHAT_ID` conseguem disparar — qualquer outro chat
    recebe um aviso de "não autorizado" e nada acontece.
    Para conferir que o webhook está ativo: `GET
    https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo`.

## TradingView (opcional — o Data Engine já funciona sem isso)

12. **Webhook** — configurar o alerta do TradingView para enviar POST
    para `https://api.alphaquantx.com/webhooks/tradingview` com o header
    `X-Signature` calculado via HMAC-SHA256 usando
    `TRADINGVIEW_WEBHOOK_SECRET`.

## Frontend (Vercel)

13. **Importar o repositório** na Vercel, apontando o **Root Directory**
    para `frontend/`.
14. **Environment Variable** — `NEXT_PUBLIC_API_BASE_URL` apontando para
    a URL pública da API no Render (ex.:
    `https://api.alphaquantx.com`). Sem isso o frontend cai no fallback
    `http://localhost:8000`, que não funciona em produção.
15. **Build** — a Vercel detecta Next.js automaticamente
    (`npm install && npm run build`); nenhuma configuração extra é
    necessária além da env var acima.
16. **Domínio** — preparar `app.alphaquantx.com`.
17. **Antes de expor publicamente**: rodar `npm audit fix` (ou migrar
    para o Next 16) — a linha 14.x usada aqui tem CVEs conhecidas mesmo
    na última versão patch (ver `frontend/README.md`).

## Confirmação final

18. **Health Check** — `GET /health` deve reportar todos os serviços
    `ONLINE` antes de considerar `TEST_MODE=false` (seção 53 — só depois
    de API, worker, Telegram, database, health checks, dedup e testes
    todos funcionando).
19. **Smoke test do Dashboard** — abrir `/`, `/scanner`, `/playbooks` e
    `/health` no frontend deployado e confirmar que os dados batem com o
    que a API retorna diretamente.
