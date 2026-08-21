"""
ALPHAQUANT SCANNER WORKER

Processo de longa duração (Render Background Worker). NÃO depende do
frontend nem do navegador estar aberto. Fica ativo continuamente:
madrugada, fim de semana, feriado.

Fluxo por ciclo (seção 68 — ordem obrigatória, nunca invertida):
DATA -> CONTEXT -> REGIME -> HTF -> MTF -> LTF -> LIQUIDITY -> VOLUME ->
SMART MONEY -> WYCKOFF -> PLAYBOOK -> ENTRY -> STOP -> TARGETS -> RR ->
EXPECTANCY -> SCORE -> QUALITY FILTER -> DECISION ENGINE -> TELEGRAM
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.models import ScannerEvent, StrategyStatus, SystemHealth
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.engines.alert_engine import decide_alert
from alphaquant_core.engines.bybit_data_engine import BybitMarketDataClient
from alphaquant_core.engines.data_engine import MarketDataError
from alphaquant_core.playbooks.runner import compute_htf_regime, htf_timeframe_for, scan_and_score
from alphaquant_core.services import strategy_service
from alphaquant_core.services.lock_service import release_lock, try_acquire_lock
from alphaquant_core.services.manual_scan_service import claim_pending_manual_scan
from alphaquant_core.services.trade_service import apply_price_update, list_open_trades
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.formatting import (
    format_scan_started_message,
    format_system_error_message,
    format_system_online_message,
    format_system_recovered_message,
    format_trade_update_message,
)
from alphaquant_core.telegram.queue import enqueue_alert, process_pending_alerts
from alphaquant_core.telegram.summary import compute_cycle_summary, format_cycle_summary_message
from .scheduler import seconds_until_next_boundary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("alphaquant.worker")


def emit_heartbeat(db: Session, assets_scanned: int, opportunities_found: int, errors: int, latency_ms: float) -> None:
    row = db.execute(select(SystemHealth).where(SystemHealth.service == "worker")).scalar_one_or_none()
    if row is None:
        row = SystemHealth(service="worker")
        db.add(row)
    row.status = "ONLINE" if errors == 0 else "DEGRADED"
    row.last_heartbeat = datetime.now(timezone.utc)
    row.latency_ms = latency_ms
    row.error = None if errors == 0 else f"{errors} error(s) in last cycle"
    db.commit()
    logger.info(
        "heartbeat assets_scanned=%s opportunities_found=%s errors=%s latency_ms=%.1f",
        assets_scanned, opportunities_found, errors, latency_ms,
    )


def _worker_health_status(db: Session) -> str | None:
    row = db.execute(select(SystemHealth).where(SystemHealth.service == "worker")).scalar_one_or_none()
    return row.status if row else None


def notify_health_transition(db: Session, telegram_client: TelegramClient, previous_status: str | None) -> None:
    """
    Seção 42/48 — SYSTEM_ERROR só na transição ONLINE -> DEGRADED (nunca
    repetido a cada ciclo enquanto o erro persiste), e um aviso de
    recuperação na volta DEGRADED -> ONLINE.
    """
    settings = get_settings()
    row = db.execute(select(SystemHealth).where(SystemHealth.service == "worker")).scalar_one_or_none()
    if row is None:
        return
    if previous_status != "DEGRADED" and row.status == "DEGRADED":
        text = format_system_error_message("worker", row.error or "erro desconhecido")
        result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
        if not result.success:
            logger.error("falha ao enviar SYSTEM_ERROR: %s", result.error)
    elif previous_status == "DEGRADED" and row.status == "ONLINE":
        text = format_system_recovered_message("worker")
        result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
        if not result.success:
            logger.error("falha ao enviar mensagem de recuperação: %s", result.error)


def run_trade_tracking_cycle(db: Session, client: BybitMarketDataClient, telegram_client: TelegramClient) -> tuple[int, int]:
    """
    Seção 86 — a cada ciclo, atualiza o preço de toda Trade aberta
    (seção 77-106) e envia Telegram para eventos relevantes (TP, stop,
    breakeven, fechamento). Falha ao buscar preço de UM ativo nunca
    derruba o tracking dos outros (mesma filosofia de resiliência do
    scan cycle — seção 60).
    """
    settings = get_settings()
    open_trades = list_open_trades(db)
    updated = 0
    errors = 0
    price_cache: dict[str, float | None] = {}

    for trade in open_trades:
        if trade.asset not in price_cache:
            try:
                price_cache[trade.asset] = client.get_ticker_price(trade.asset)
            except MarketDataError as exc:
                logger.warning("falha ao buscar preço para tracking de trade asset=%s: %s", trade.asset, exc)
                price_cache[trade.asset] = None
                errors += 1

        price = price_cache[trade.asset]
        if price is None:
            continue

        try:
            events = apply_price_update(db, trade, price)
        except Exception:
            logger.exception("falha ao atualizar trade id=%s", trade.id)
            errors += 1
            continue

        updated += 1
        skip_closed = False
        for event in events:
            if event.event_type == "RESULT":
                continue  # metadado interno (usado só para compor CLOSED/STOP), não vira mensagem própria
            if event.event_type == "CLOSED" and skip_closed:
                # a mensagem do TP que acabou de fechar a posição já diz
                # "Operação encerrada" — evita duplicar com um segundo
                # Telegram só para o evento CLOSED subsequente.
                continue
            text = format_trade_update_message(trade, event)
            result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
            if not result.success:
                logger.error("falha ao enviar atualização de trade id=%s evento=%s: %s", trade.id, event.event_type, result.error)
            skip_closed = event.event_type.endswith("_HIT")

    return updated, errors


def resolve_scan_universe(client: BybitMarketDataClient) -> list[str]:
    """
    Seção 4 — universo de moedas. `SCAN_ASSETS=AUTO` (novo modo, opt-in —
    o padrão continua sendo a lista manual existente, para não mudar o
    comportamento de um worker já em produção sem uma escolha explícita)
    descobre os símbolos USDT Perpetual elegíveis direto na Bybit,
    ranqueados por liquidez, respeitando MIN_SYMBOLS/MAX_SYMBOLS.
    """
    settings = get_settings()
    if settings.SCAN_ASSETS.strip().upper() != "AUTO":
        return settings.scan_assets

    try:
        return client.discover_usdt_perpetual_symbols(
            min_symbols=settings.MIN_SYMBOLS, max_symbols=settings.MAX_SYMBOLS,
        )
    except MarketDataError:
        logger.exception(
            "falha ao descobrir universo dinâmico de símbolos na Bybit — "
            "nenhum símbolo inventado, ciclo atual roda com lista vazia"
        )
        return []


def wait_for_next_cycle(db_factory, settings) -> tuple[bool, str | None]:
    """
    Seção 6 (fechamento de vela) + comando manual `/analisar` (webhook
    Telegram): espera o próximo boundary de SCAN_INTERVAL_MINUTES, mas
    faz polling curto (`MANUAL_SCAN_POLL_SECONDS`) em `manual_scan_requests`
    o tempo todo — se alguém pedir uma análise manual, a espera é
    interrompida na hora, sem esperar o resto do ciclo agendado.

    Devolve (manual, requested_by_username): manual=True se a análise
    foi disparada por /analisar, False se foi o fechamento de vela normal.
    """
    deadline = time.monotonic() + seconds_until_next_boundary(settings.SCAN_INTERVAL_MINUTES)
    while True:
        db = db_factory()
        try:
            claimed = claim_pending_manual_scan(db)
        finally:
            db.close()
        if claimed is not None:
            return True, claimed.requested_by_username

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, None
        time.sleep(min(settings.MANUAL_SCAN_POLL_SECONDS, remaining))


def run_scan_cycle(
    db: Session, telegram_client: TelegramClient, symbols: list[str] | None = None,
) -> tuple[int, int, int]:
    """
    Pipeline principal da seção 68 fechado ponta a ponta (Fases 3-9):
    Data Engine -> Playbook Engine -> Targets/Score -> Quality Filter ->
    Decision Engine -> Alert Engine -> Telegram. Cada `Opportunity`
    persistida já sai com `status`/`decision` reais, e cada decisão
    genuinamente nova (seção 19-20: dedup + cooldown de 30min) vira um
    alerta enfileirado e enviado ao fim do ciclo.

    Fase 8 fechou duas lacunas da Fase 7 (regime HTF real + lock
    distribuído). Fase 9 fecha a comunicação: `decide_alert` decide SE
    alertar (nunca a cada variação marginal), `enqueue_alert` grava
    `PENDING` na tabela `alerts`, e `process_pending_alerts` (uma vez por
    ciclo, em lote) chama a API do Telegram de verdade com retry.

    Fase 4 (evolução) trocou a fonte de dados para a Bybit (seção 3) e
    tornou o universo de ativos descobrível dinamicamente (seção 4, via
    `resolve_scan_universe` — opt-in com `SCAN_ASSETS=AUTO`).
    """
    settings = get_settings()
    client = BybitMarketDataClient()
    if symbols is None:
        symbols = resolve_scan_universe(client)

    assets_scanned = 0
    opportunities_found = 0
    errors = 0

    for symbol in symbols:
        htf_regime_cache: dict[str, str | None] = {}

        for timeframe in settings.scan_timeframes:
            lock_key = f"scan:{symbol}:{timeframe}"
            if not try_acquire_lock(db, lock_key):
                logger.info("scan skip (locked by outro processo) symbol=%s timeframe=%s", symbol, timeframe)
                continue

            try:
                htf_tf = htf_timeframe_for(timeframe)
                if htf_tf is not None and htf_tf not in htf_regime_cache:
                    htf_regime_cache[htf_tf] = compute_htf_regime(db, symbol, htf_tf, client=client)
                htf_regime = htf_regime_cache.get(htf_tf) if htf_tf else None

                ctx, results, opportunities = scan_and_score(db, symbol, timeframe, client=client, htf_regime=htf_regime)
                assets_scanned += 1
                opportunities_found += len(opportunities)
                matched = [r for r in results if r.matched]
                logger.info(
                    "scan ok symbol=%s timeframe=%s regime=%s htf_regime=%s playbooks_matched=%s",
                    symbol, timeframe, ctx.regime, htf_regime, [r.playbook for r in matched],
                )
                for opp in opportunities:
                    logger.info(
                        "OPPORTUNITY symbol=%s timeframe=%s playbook=%s direction=%s score=%.1f rr=%s "
                        "entry=%s stop=%s decision=%s status=%s",
                        symbol, timeframe, opp.playbook, opp.direction.value, opp.score, opp.rr, opp.entry, opp.stop,
                        opp.decision.value if opp.decision is not None else None, opp.status.value,
                    )
                    alert_type = decide_alert(db, opp)
                    if alert_type is not None:
                        enqueue_alert(db, opp, alert_type)
                        logger.info(
                            "alert enqueued symbol=%s timeframe=%s playbook=%s alert_type=%s",
                            symbol, timeframe, opp.playbook, alert_type.value,
                        )
            except MarketDataError as exc:
                errors += 1
                logger.error("falha ao coletar %s %s: %s", symbol, timeframe, exc)
                db.add(ScannerEvent(
                    event_type="data_engine_error",
                    asset=symbol,
                    payload={"timeframe": timeframe, "error": str(exc)},
                ))
                db.commit()
            except Exception:
                errors += 1
                logger.exception("erro inesperado no ciclo de %s %s", symbol, timeframe)
                db.rollback()
            finally:
                release_lock(db, lock_key)

    sent, failed = process_pending_alerts(db, telegram_client)
    if sent or failed:
        logger.info("telegram queue processed sent=%s failed=%s", sent, failed)

    return assets_scanned, opportunities_found, errors


def main() -> None:
    settings = get_settings()
    logger.info("ALPHAQUANT X worker starting | environment=%s test_mode=%s", settings.ENVIRONMENT, settings.TEST_MODE)

    telegram_client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)

    # Seção 7 — primeira mensagem ao ligar o sistema, sempre que o
    # processo sobe com sucesso (antes de esperar o primeiro fechamento
    # de vela). Contagens reais: nunca "N ativas" fixo no texto.
    db = SessionLocal()
    try:
        active_strategies = len(strategy_service.list_strategies(db, status=StrategyStatus.ACTIVE))
    except Exception:
        logger.exception("falha ao contar estratégias ativas para a mensagem de boot")
        active_strategies = 0
    finally:
        db.close()

    try:
        symbols_count = len(resolve_scan_universe(BybitMarketDataClient()))
    except Exception:
        logger.exception("falha ao resolver universo de símbolos para a mensagem de boot")
        symbols_count = 0

    boot_text = format_system_online_message(active_strategies, symbols_count, settings.SCAN_INTERVAL_MINUTES)
    boot_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, boot_text)
    if not boot_result.success:
        logger.error("falha ao enviar mensagem de boot: %s", boot_result.error)

    while True:
        # Seção 6 — o ciclo NUNCA roda "60 segundos depois de o processo
        # iniciar": ele espera o fechamento real da vela de
        # SCAN_INTERVAL_MINUTES (00:00, 00:15, 00:30, ...), inclusive no
        # primeiro ciclo após o boot — a NÃO ser que um /analisar chegue
        # antes disso, aí a espera é cortada na hora (`wait_for_next_cycle`).
        manual, requested_by = wait_for_next_cycle(SessionLocal, settings)
        if manual:
            logger.info("análise manual disparada via Telegram (/analisar) por %s", requested_by or "desconhecido")
        else:
            logger.info("fechamento de vela de %sm atingido, iniciando ciclo", settings.SCAN_INTERVAL_MINUTES)

        cycle_started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        db = SessionLocal()
        try:
            previous_status = _worker_health_status(db)

            # Universo resolvido uma única vez por ciclo — usado tanto na
            # mensagem de início quanto no scan em si, sem descobrir os
            # símbolos duas vezes na Bybit.
            symbols = resolve_scan_universe(BybitMarketDataClient())

            started_text = format_scan_started_message(manual, len(symbols), requested_by)
            started_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, started_text)
            if not started_result.success:
                logger.error("falha ao enviar mensagem de início de ciclo: %s", started_result.error)

            assets_scanned, opportunities_found, errors = run_scan_cycle(db, telegram_client, symbols=symbols)

            # Seção 86 — tracking das Trades abertas roda todo ciclo,
            # junto do scanner (mesma cadência de 15min); erros de
            # tracking contam para o health check, mas nunca derrubam o
            # scan em si (já rodou antes desta chamada).
            _trades_updated, trade_errors = run_trade_tracking_cycle(db, BybitMarketDataClient(), telegram_client)
            errors += trade_errors

            # Sempre manda o resumo do ciclo — "fique de olho" ou "nada
            # ainda" — nunca só silêncio até achar algo (pedido do usuário).
            cycle_summary = compute_cycle_summary(db, since=cycle_started_at)
            summary_text = format_cycle_summary_message(cycle_summary, manual, assets_scanned)
            summary_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, summary_text)
            if not summary_result.success:
                logger.error("falha ao enviar resumo de ciclo: %s", summary_result.error)

            latency_ms = (time.monotonic() - started) * 1000
            emit_heartbeat(db, assets_scanned, opportunities_found, errors, latency_ms)
            notify_health_transition(db, telegram_client, previous_status)
        except Exception:
            logger.exception("scan cycle failed")
        finally:
            db.close()


if __name__ == "__main__":
    main()
