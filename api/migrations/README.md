# Migrations — AlphaQuant X

Gerenciadas por Alembic, vivem dentro do serviço `api` (a API é quem
possui a responsabilidade de schema; o Worker só lê/escreve dados).

O `env.py` importa `alphaquant_core.db.models` (pacote compartilhado) para
que `target_metadata` sempre reflita o schema real usado pelo ORM — API e
Worker nunca podem divergir.

## Comandos

```bash
# aplicar todas as migrations pendentes
alembic upgrade head

# reverter tudo
alembic downgrade base

# criar uma nova revisão vazia após alterar shared/alphaquant_core/db/models.py
alembic revision -m "descrição da mudança"
```

## Revisões

- `0001_initial_schema` — cria as 9 tabelas e os 6 tipos ENUM do schema
  oficial (seção 11 do master prompt): assets, candles, playbooks,
  opportunities, evidence, alerts, scanner_events, system_health,
  backtests. Testada de ponta a ponta (`upgrade` → `downgrade` →
  `upgrade`) contra um PostgreSQL 16 real antes de ser entregue.

## Por que os ENUMs são criados manualmente no upgrade()

`postgresql.ENUM(..., create_type=False)` é usado nas colunas porque os
tipos são criados/removidos explicitamente com `checkfirst=True` no início
de `upgrade()`/fim de `downgrade()`. Sem isso, `create_table` tentaria
criar o mesmo tipo de novo e falharia com "type already exists".
