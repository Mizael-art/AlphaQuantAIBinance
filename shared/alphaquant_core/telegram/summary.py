"""
Analytics (Fase 12 — seções 21-22 do master prompt).

Resumo diário e relatório semanal, calculados exclusivamente a partir de
`opportunities` já persistidas — nenhum dado de P&L/trade realizado é
usado porque o sistema ainda não rastreia execução real de ordens (isso
é explicitamente fora de escopo: o AlphaQuant X não envia ordens, seção
1 do master prompt). Métricas que dependeriam disso (profit factor,
expectância real) ficam para quando a Fase 13 (Backtest) e um eventual
módulo de tracking de posições existirem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Opportunity, OpportunityStatus


@dataclass(frozen=True)
class DailySummary:
    date: str
    analyzed: int
    score_ge_70: int
    score_ge_80: int
    score_ge_90: int
    confirmed: int
    future: int
    rejected: int
    top_playbook: str | None
    best_asset: str | None
    average_score: float | None
    risk_status: str


@dataclass(frozen=True)
class WeeklyPlaybookStat:
    playbook: str
    count: int
    average_score: float


@dataclass(frozen=True)
class WeeklyAssetStat:
    asset: str
    count: int
    average_score: float


@dataclass(frozen=True)
class WeeklyReport:
    period_start: str
    period_end: str
    total_opportunities: int
    average_score: float | None
    top_playbooks: list[WeeklyPlaybookStat] = field(default_factory=list)
    best_assets: list[WeeklyAssetStat] = field(default_factory=list)
    worst_assets: list[WeeklyAssetStat] = field(default_factory=list)
    still_in_formation: int = 0


def compute_daily_summary(db: Session, now: datetime | None = None) -> DailySummary:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    base = select(Opportunity).where(Opportunity.updated_at.between(since, now))

    analyzed = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    score_70 = db.execute(select(func.count()).select_from(base.where(Opportunity.score >= 70).subquery())).scalar() or 0
    score_80 = db.execute(select(func.count()).select_from(base.where(Opportunity.score >= 80).subquery())).scalar() or 0
    score_90 = db.execute(select(func.count()).select_from(base.where(Opportunity.score >= 90).subquery())).scalar() or 0
    confirmed = db.execute(
        select(func.count()).select_from(base.where(Opportunity.status == OpportunityStatus.CONFIRMED).subquery())
    ).scalar() or 0
    future = db.execute(
        select(func.count()).select_from(base.where(Opportunity.status == OpportunityStatus.FORMATION).subquery())
    ).scalar() or 0
    rejected = db.execute(
        select(func.count()).select_from(base.where(Opportunity.status == OpportunityStatus.INVALIDATED).subquery())
    ).scalar() or 0

    top_playbook_row = db.execute(
        select(Opportunity.playbook, func.count().label("n"))
        .where(Opportunity.updated_at.between(since, now))
        .group_by(Opportunity.playbook)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    top_playbook = top_playbook_row[0] if top_playbook_row else None

    best_asset_row = db.execute(
        select(Opportunity.asset, func.avg(Opportunity.score).label("avg_score"))
        .where(Opportunity.updated_at.between(since, now))
        .group_by(Opportunity.asset)
        .order_by(func.avg(Opportunity.score).desc())
        .limit(1)
    ).first()
    best_asset = best_asset_row[0] if best_asset_row else None

    avg_score = db.execute(select(func.avg(Opportunity.score)).where(Opportunity.updated_at.between(since, now))).scalar()

    # Heurística simples derivada de dados reais (não é gestão de risco de
    # posição real, que exigiria tracking de execução — fora de escopo):
    # se a maioria das oportunidades do dia foi reprovada, sinaliza atenção.
    risk_status = "Normal"
    if analyzed > 0 and (rejected / analyzed) > 0.7:
        risk_status = "Atenção — alta taxa de reprovação no dia"

    return DailySummary(
        date=now.date().isoformat(),
        analyzed=analyzed, score_ge_70=score_70, score_ge_80=score_80, score_ge_90=score_90,
        confirmed=confirmed, future=future, rejected=rejected,
        top_playbook=top_playbook, best_asset=best_asset,
        average_score=float(avg_score) if avg_score is not None else None,
        risk_status=risk_status,
    )


def format_daily_summary_message(summary: DailySummary) -> str:
    lines = [
        "📊 ALPHAQUANT X",
        "DAILY MARKET SUMMARY",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "Oportunidades analisadas:",
        str(summary.analyzed),
        "",
        "Score ≥70:",
        str(summary.score_ge_70),
        "",
        "Score ≥80:",
        str(summary.score_ge_80),
        "",
        "Score ≥90:",
        str(summary.score_ge_90),
        "",
        "Oportunidades confirmadas:",
        str(summary.confirmed),
        "",
        "Oportunidades futuras:",
        str(summary.future),
        "",
        "Reprovadas:",
        str(summary.rejected),
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "🏆 TOP PLAYBOOK",
        "",
        summary.top_playbook or "—",
        "",
        "📈 MELHOR ATIVO",
        "",
        summary.best_asset or "—",
        "",
        "📊 SCORE MÉDIO",
        "",
        f"{summary.average_score:.1f}" if summary.average_score is not None else "—",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "🛡️ RISK STATUS",
        "",
        summary.risk_status,
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)


def compute_weekly_report(db: Session, now: datetime | None = None) -> WeeklyReport:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    total = db.execute(
        select(func.count()).select_from(Opportunity).where(Opportunity.updated_at.between(since, now))
    ).scalar() or 0
    avg_score = db.execute(
        select(func.avg(Opportunity.score)).where(Opportunity.updated_at.between(since, now))
    ).scalar()

    playbook_rows = db.execute(
        select(Opportunity.playbook, func.count().label("n"), func.avg(Opportunity.score).label("avg_score"))
        .where(Opportunity.updated_at.between(since, now))
        .group_by(Opportunity.playbook)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    top_playbooks = [WeeklyPlaybookStat(playbook=r[0], count=r[1], average_score=float(r[2])) for r in playbook_rows]

    asset_rows = db.execute(
        select(Opportunity.asset, func.count().label("n"), func.avg(Opportunity.score).label("avg_score"))
        .where(Opportunity.updated_at.between(since, now))
        .group_by(Opportunity.asset)
        .having(func.count() >= 1)
        .order_by(func.avg(Opportunity.score).desc())
        .limit(3)
    ).all()
    best_assets = [WeeklyAssetStat(asset=r[0], count=r[1], average_score=float(r[2])) for r in asset_rows]

    worst_asset_rows = db.execute(
        select(Opportunity.asset, func.count().label("n"), func.avg(Opportunity.score).label("avg_score"))
        .where(Opportunity.updated_at.between(since, now))
        .group_by(Opportunity.asset)
        .having(func.count() >= 1)
        .order_by(func.avg(Opportunity.score).asc())
        .limit(3)
    ).all()
    worst_assets = [WeeklyAssetStat(asset=r[0], count=r[1], average_score=float(r[2])) for r in worst_asset_rows]

    still_forming = db.execute(
        select(func.count()).select_from(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.FORMATION)
    ).scalar() or 0

    return WeeklyReport(
        period_start=since.date().isoformat(), period_end=now.date().isoformat(),
        total_opportunities=total, average_score=float(avg_score) if avg_score is not None else None,
        top_playbooks=top_playbooks, best_assets=best_assets, worst_assets=worst_assets,
        still_in_formation=still_forming,
    )


def format_weekly_report_message(report: WeeklyReport) -> str:
    lines = [
        "📅 ALPHAQUANT X",
        "WEEKLY REPORT",
        f"{report.period_start} — {report.period_end}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "Total de oportunidades:",
        str(report.total_opportunities),
        "",
        "Score médio da semana:",
        f"{report.average_score:.1f}" if report.average_score is not None else "—",
        "",
        "Setups ainda em validação:",
        str(report.still_in_formation),
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "🏆 TOP PLAYBOOKS (por volume)",
        "",
        *[f"{p.playbook}: {p.count} ocorrências, score médio {p.average_score:.1f}" for p in report.top_playbooks],
        "",
        "📈 MELHORES ATIVOS (por score médio)",
        "",
        *[f"{a.asset}: {a.average_score:.1f} ({a.count} oportunidades)" for a in report.best_assets],
        "",
        "📉 PIORES ATIVOS (por score médio)",
        "",
        *[f"{a.asset}: {a.average_score:.1f} ({a.count} oportunidades)" for a in report.worst_assets],
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "ℹ️ Este relatório NÃO inclui profit factor, expectância ou",
        "drawdown reais — o sistema não executa ordens (ver Fase 13,",
        "Backtest, para validação estatística por Playbook).",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)
