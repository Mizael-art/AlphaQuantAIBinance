from datetime import datetime, timedelta, timezone

from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import scan_and_score
from alphaquant_core.telegram.summary import compute_cycle_summary, format_cycle_summary_message

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


def test_cycle_summary_with_nothing_found_still_sends_a_clear_message(db_session):
    """
    O pedido original: o bot NUNCA fica em silêncio depois de um ciclo,
    mesmo quando não achou nenhum setup — sempre manda "nada relevante",
    nunca só o sinal quando (e se) achar algo.
    """
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    now = since + timedelta(minutes=15)
    summary = compute_cycle_summary(db_session, since=since, now=now)

    assert summary.top_opportunities == []
    assert summary.forming == []

    text = format_cycle_summary_message(summary, manual=False, assets_scanned=87)
    assert "CICLO DE ANÁLISE CONCLUÍDO" in text
    assert "Nada relevante por enquanto." in text
    assert "87" in text


def test_cycle_summary_manual_header_differs_from_automatic(db_session):
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    now = since + timedelta(minutes=15)
    summary = compute_cycle_summary(db_session, since=since, now=now)

    manual_text = format_cycle_summary_message(summary, manual=True, assets_scanned=10)
    auto_text = format_cycle_summary_message(summary, manual=False, assets_scanned=10)

    assert "ANÁLISE MANUAL CONCLUÍDA" in manual_text
    assert "CICLO DE ANÁLISE CONCLUÍDO" in auto_text


def test_cycle_summary_lists_real_opportunities_found_in_the_window(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(
        db_session, "CYCLEUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH",
    )
    assert opportunities

    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    since = now - timedelta(minutes=15)
    summary = compute_cycle_summary(db_session, since=since, now=now)

    confirmed = [o for o in opportunities if o.status.value == "CONFIRMED"]
    forming = [o for o in opportunities if o.status.value == "FORMATION"]
    # A suíte compartilha o mesmo Postgres efêmero entre arquivos de
    # teste (mesmo comportamento documentado em
    # test_hourly_intelligence.py): outras oportunidades da mesma janela
    # podem ranquear na frente de CYCLEUSDT no TOP 5 — o que importa
    # aqui é que a lista vem preenchida e bem formada quando há
    # oportunidades reais, não a posição exata de um ativo específico.
    if confirmed:
        assert len(summary.top_opportunities) > 0
    if forming:
        assert len(summary.forming) > 0

    text = format_cycle_summary_message(summary, manual=False, assets_scanned=1)
    if confirmed or forming:
        assert "Nada relevante" not in text
