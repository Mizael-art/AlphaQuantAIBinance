"""
Analytics (Fase 12 — seções 21-22 do master prompt; seção 10 da
evolução Fase 4/7 — Market Intelligence horário).

Resumo diário, relatório semanal e Market Intelligence horário,
calculados exclusivamente a partir de `opportunities`/`scanner_events`
já persistidas — nenhum dado de P&L/trade realizado é usado aqui (isso
vive em `trade_service`/`trades`, seções 77-106). Métricas que
dependeriam de execução real de ordens continuam fora de escopo (seção
1: o AlphaQuant X não envia ordens).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Opportunity, OpportunityStatus, ScannerEvent


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


@dataclass(frozen=True)
class HourlyOpportunity:
    asset: str
    playbook: str
    score: float
    direction: str
    status: str


@dataclass(frozen=True)
class HourlyRejection:
    asset: str
    playbook: str
    reason: str


@dataclass(frozen=True)
class HourlyIntelligence:
    period_start: str
    period_end: str
    top_opportunities: list[HourlyOpportunity] = field(default_factory=list)
    forming: list[HourlyOpportunity] = field(default_factory=list)
    rejected: list[HourlyRejection] = field(default_factory=list)
    data_unavailable_assets: list[str] = field(default_factory=list)


def compute_hourly_intelligence(db: Session, now: datetime | None = None, window_minutes: int = 60) -> HourlyIntelligence:
    """
    Seção 10 — MARKET INTELLIGENCE. Mesma fonte de verdade do resumo
    diário (`opportunities` já persistidas), só que numa janela de 1h
    (`REPORT_INTERVAL_MINUTES`) em vez de 24h, com o TOP ranqueado por
    score e as seções FORMING/REJECTED separadas (seção 55: setup ≠
    sinal — nunca listar FORMATION como se fosse entrada).
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(minutes=window_minutes)

    top_rows = db.execute(
        select(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.CONFIRMED)
        .order_by(Opportunity.score.desc())
        .limit(5)
    ).scalars().all()

    forming_rows = db.execute(
        select(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.FORMATION)
        .order_by(Opportunity.score.desc())
        .limit(5)
    ).scalars().all()

    rejected_rows = db.execute(
        select(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.INVALIDATED)
        .order_by(Opportunity.updated_at.desc())
        .limit(3)
    ).scalars().all()

    unavailable_rows = db.execute(
        select(ScannerEvent.asset)
        .where(ScannerEvent.timestamp.between(since, now), ScannerEvent.event_type == "data_engine_error")
        .distinct()
        .limit(10)
    ).scalars().all()

    def _to_hourly(o: Opportunity) -> HourlyOpportunity:
        return HourlyOpportunity(
            asset=o.asset, playbook=o.playbook, score=float(o.score),
            direction=o.direction.value, status=o.status.value,
        )

    def _to_rejection(o: Opportunity) -> HourlyRejection:
        snapshot = o.audit_snapshot or {}
        reasons = snapshot.get("quality_filter", {}).get("reasons", [])
        reason = reasons[0] if reasons else "condições deixaram de ser atendidas"
        return HourlyRejection(asset=o.asset, playbook=o.playbook, reason=reason)

    return HourlyIntelligence(
        period_start=since.isoformat(), period_end=now.isoformat(),
        top_opportunities=[_to_hourly(o) for o in top_rows],
        forming=[_to_hourly(o) for o in forming_rows],
        rejected=[_to_rejection(o) for o in rejected_rows],
        data_unavailable_assets=list(unavailable_rows),
    )


def format_hourly_intelligence_message(intel: HourlyIntelligence) -> str:
    lines = [
        "📊 ALPHAQUANT X — MARKET INTELLIGENCE",
        "",
        f"🕐 Última hora ({intel.period_start[11:16]} — {intel.period_end[11:16]} UTC)",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "🔥 MELHORES OPORTUNIDADES",
        "",
    ]
    if intel.top_opportunities:
        lines += [
            f"{i + 1}. {o.asset} — {o.playbook} — score {o.score:.0f} — {o.direction}"
            for i, o in enumerate(intel.top_opportunities)
        ]
    else:
        lines.append("Não foram encontradas entradas de alta qualidade nesta janela.")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "", "👀 SETUPS EM FORMAÇÃO", ""]
    if intel.forming:
        lines += [f"• {o.asset} — {o.playbook} — score {o.score:.0f}" for o in intel.forming]
    else:
        lines.append("Nenhum setup em formação relevante.")

    if intel.data_unavailable_assets:
        lines += ["", "━━━━━━━━━━━━━━━━━━", "", "⚠️ ATENÇÃO", ""]
        lines.append("Dados indisponíveis nesta janela: " + ", ".join(intel.data_unavailable_assets))

    lines += ["", "━━━━━━━━━━━━━━━━━━", "", "❌ REJEITADOS", ""]
    if intel.rejected:
        lines += [f"• {r.asset} — {r.playbook}: {r.reason}" for r in intel.rejected]
    else:
        lines.append("Nenhuma rejeição relevante nesta janela.")

    lines += [
        "", "━━━━━━━━━━━━━━━━━━", "",
        "⚠️ Setup identificado ≠ garantia de resultado. Gestão de risco é obrigatória.",
        "",
        "ALPHAQUANT X",
    ]
    return "\n".join(lines)


def compute_cycle_summary(db: Session, since: datetime, now: datetime | None = None) -> HourlyIntelligence:
    """
    Mesmo cálculo de `compute_hourly_intelligence`, mas com janela
    explícita (o próprio ciclo de scan que acabou de rodar, seção 68 —
    automático a cada SCAN_INTERVAL_MINUTES ou manual via /analisar) em
    vez de uma janela fixa de 1h. Reaproveita `HourlyIntelligence` como
    estrutura de dados porque a pergunta é a mesma: "o que apareceu
    (ou não) nesta janela?".
    """
    now = now or datetime.now(timezone.utc)

    top_rows = db.execute(
        select(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.CONFIRMED)
        .order_by(Opportunity.score.desc())
        .limit(5)
    ).scalars().all()

    forming_rows = db.execute(
        select(Opportunity)
        .where(Opportunity.updated_at.between(since, now), Opportunity.status == OpportunityStatus.FORMATION)
        .order_by(Opportunity.score.desc())
        .limit(5)
    ).scalars().all()

    unavailable_rows = db.execute(
        select(ScannerEvent.asset)
        .where(ScannerEvent.timestamp.between(since, now), ScannerEvent.event_type == "data_engine_error")
        .distinct()
        .limit(10)
    ).scalars().all()

    def _to_hourly(o: Opportunity) -> HourlyOpportunity:
        return HourlyOpportunity(
            asset=o.asset, playbook=o.playbook, score=float(o.score),
            direction=o.direction.value, status=o.status.value,
        )

    return HourlyIntelligence(
        period_start=since.isoformat(), period_end=now.isoformat(),
        top_opportunities=[_to_hourly(o) for o in top_rows],
        forming=[_to_hourly(o) for o in forming_rows],
        rejected=[],
        data_unavailable_assets=list(unavailable_rows),
    )


def format_cycle_summary_message(intel: HourlyIntelligence, manual: bool, assets_scanned: int) -> str:
    """
    Enviada ao FIM de todo ciclo de scan (manual ou automático) — o
    "e aí, achou alguma coisa?" que o usuário sempre recebe, mesmo
    quando a resposta é "nada ainda". As oportunidades CONFIRMED/
    FORMATION relevantes já saíram como mensagem própria (sinal/future,
    seção 16/17) via `process_pending_alerts`; esta mensagem é só o
    apanhado geral do ciclo, nunca duplica o conteúdo do sinal em si.
    """
    header = "✅ ANÁLISE MANUAL CONCLUÍDA" if manual else "✅ CICLO DE ANÁLISE CONCLUÍDO"
    lines = [header, "", f"Ativos analisados: {assets_scanned}", "", "━━━━━━━━━━━━━━━━━━", ""]

    has_something = bool(intel.top_opportunities or intel.forming)

    if intel.top_opportunities:
        lines += ["🎯 SINAIS CONFIRMADOS NESTE CICLO", ""]
        lines += [
            f"{i + 1}. {o.asset} — {o.playbook} — score {o.score:.0f} — {o.direction}"
            for i, o in enumerate(intel.top_opportunities)
        ]
        lines += ["", "(mensagem de sinal detalhada enviada separadamente acima/abaixo)", ""]

    if intel.forming:
        lines += ["👀 FIQUE DE OLHO — setups em formação", ""]
        lines += [f"• {o.asset} — {o.playbook} — score {o.score:.0f}" for o in intel.forming]
        lines += [""]

    if not has_something:
        lines += ["Nada relevante por enquanto.", "Nenhum setup em formação ou confirmado neste ciclo.", ""]

    if intel.data_unavailable_assets:
        lines += ["⚠️ Dados indisponíveis para: " + ", ".join(intel.data_unavailable_assets), ""]

    lines += ["━━━━━━━━━━━━━━━━━━", "", "ALPHAQUANT X"]
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
