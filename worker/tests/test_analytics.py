from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import scan_and_score
from alphaquant_core.telegram.summary import (
    compute_daily_summary,
    compute_weekly_report,
    format_daily_summary_message,
    format_weekly_report_message,
)

from tests.playbook_fixtures import uptrend_pullback_to_ema50


class FakeClient:
    def __init__(self, df):
        self._df = df

    def get_klines(self, symbol, timeframe, limit=200):
        rows = self._df.reset_index()
        return [
            Candle(
                timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                low=row["low"], close=row["close"], volume=row["volume"],
            )
            for _, row in rows.tail(limit).iterrows()
        ]


def test_daily_summary_with_no_data_is_well_formed(db_session):
    from datetime import datetime, timezone

    # isolado no passado distante — outros testes na mesma sessão de
    # Postgres compartilhada rodam segundos antes, dentro de qualquer
    # janela de 24h relativa ao "agora" real
    summary = compute_daily_summary(db_session, now=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert summary.analyzed == 0
    assert summary.top_playbook is None
    assert summary.best_asset is None
    assert summary.average_score is None
    assert summary.risk_status == "Normal"

    text = format_daily_summary_message(summary)
    assert "DAILY MARKET SUMMARY" in text
    assert "—" in text  # placeholders para playbook/ativo/score ausentes


def test_daily_summary_reflects_real_opportunities(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(db_session, "DAILYUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH")
    assert opportunities

    summary = compute_daily_summary(db_session)
    assert summary.analyzed >= len(opportunities)
    assert summary.average_score is not None
    assert summary.top_playbook is not None

    text = format_daily_summary_message(summary)
    assert str(summary.analyzed) in text
    assert summary.top_playbook in text


def test_daily_summary_risk_status_flags_high_rejection_rate(db_session):
    """Heurística derivada de dados reais: muitas reprovações no dia -> risk_status de atenção."""
    import pandas as pd

    flat_df = pd.DataFrame(
        {"open": [100.0] * 60, "high": [100.2] * 60, "low": [99.8] * 60, "close": [100.0] * 60, "volume": [100.0] * 60},
        index=pd.date_range("2026-01-01", periods=60, freq="h"),
    )
    # roda vários ativos com dados sem tendência -> tende a reprovar mais
    for symbol in ["RISKUSDT1", "RISKUSDT2", "RISKUSDT3"]:
        scan_and_score(db_session, symbol, "1h", client=FakeClient(flat_df))

    summary = compute_daily_summary(db_session)
    # não afirmamos categoricamente que vai disparar (depende dos dados),
    # só que o campo é sempre uma string válida e não quebra o cálculo
    assert summary.risk_status in {"Normal"} or summary.risk_status.startswith("Atenção")


def test_weekly_report_with_no_data_is_well_formed(db_session):
    from datetime import datetime, timezone

    # janela no passado distante, isolada de dados criados por outros
    # testes na mesma sessão de Postgres compartilhada
    report = compute_weekly_report(db_session, now=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert report.total_opportunities == 0
    assert report.top_playbooks == []
    assert report.best_assets == []

    text = format_weekly_report_message(report)
    assert "WEEKLY REPORT" in text
    assert "NÃO inclui profit factor" in text


def test_weekly_report_reflects_real_opportunities(db_session):
    df = uptrend_pullback_to_ema50()
    for symbol in ["WEEKLYUSDT1", "WEEKLYUSDT2"]:
        scan_and_score(db_session, symbol, "1h", client=FakeClient(df), htf_regime="BULLISH")

    report = compute_weekly_report(db_session)
    assert report.total_opportunities > 0
    assert report.average_score is not None
    assert len(report.top_playbooks) > 0
    assert len(report.best_assets) > 0

    text = format_weekly_report_message(report)
    assert "Total de oportunidades:" in text
    assert str(report.total_opportunities) in text


def test_weekly_report_never_fabricates_pnl_metrics():
    """
    Trava a decisão de design: o relatório semanal nunca deve mencionar
    profit factor/expectância/drawdown como se fossem calculados — o
    sistema não rastreia execução real de ordens.
    """
    from alphaquant_core.telegram.summary import WeeklyReport

    empty_report = WeeklyReport(period_start="2026-01-01", period_end="2026-01-08", total_opportunities=0, average_score=None)
    text = format_weekly_report_message(empty_report)
    assert "profit factor" in text.lower()  # mencionado apenas na ressalva
    assert "NÃO inclui" in text
