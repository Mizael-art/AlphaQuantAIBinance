# ALPHAQUANT X — Dashboard

Next.js 14 (App Router) + TypeScript + Tailwind. Consome só a API
(`../api`) — nunca acessa o banco diretamente.

## Rodando localmente

```bash
npm install
cp .env.local.example .env.local   # aponte para a API local (padrão: localhost:8000)
npm run dev
```

## Deploy

Vercel — ver `docs/DEPLOY.md` na raiz do repositório.

## Páginas

- `/` — Dashboard principal (cards de resumo, seção 31)
- `/scanner` — Live Scanner (tabela de oportunidades, seção 32)
- `/opportunities/[id]` — Detalhe + Evidence Panel (seções 34, 36)
- `/playbooks` — Status/limiares dos 10 playbooks (seções 58-59)
- `/health` — System Health (seção 37)

## Design

Dark institutional trading terminal (seção 60): preto/grafite/branco/
cinza com acentos teal/ciano — paleta em `tailwind.config.js`.

## Pendência de produção

`npm audit` reporta CVEs conhecidas do Next.js 14.x mesmo na última
versão patch da linha (14.2.35) — a correção completa exige migrar para
o Next 16, que é uma mudança de major version fora do escopo desta
entrega. Rodar `npm audit fix --force` (ou migrar manualmente) antes de
ir para produção real — ver Fase 14 em `docs/PROJECT_PLAN.md`.
