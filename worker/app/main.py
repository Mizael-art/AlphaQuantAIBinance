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
from alphaquant_core.db.models import ScannerEvent, SystemHealth
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.engines.alert_engine import decide_alert
from alphaquant_core.engines.data_engine import BinanceMarketDataClient, BinanceRequestError
from alphaquant_core.playbooks.runner import compute_htf_regime, htf_timeframe_for, scan_and_score
from alphaquant_core.services.lock_service import release_lock, try_acquire_lock
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.queue import enqueue_alert, process_pending_alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("alphaquant.worker")

SCAN_INTERVAL_SECONDS = 60


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


def run_scan_cycle(db: Session, telegram_client: TelegramClient) -> tuple[int, int, int]:
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
    """
    settings = get_settings()
    client = BinanceMarketDataClient()

    assets_scanned = 0
    opportunities_found = 0
    errors = 0

    for symbol in settings.scan_assets:
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
                        opp.decision.value, opp.status.value,
                    )
                    alert_type = decide_alert(db, opp)
                    if alert_type is not None:
                        enqueue_alert(db, opp, alert_type)
                        logger.info(
                            "alert enqueued symbol=%s timeframe=%s playbook=%s alert_type=%s",
                            symbol, timeframe, opp.playbook, alert_type.value,
                        )
            except BinanceRequestError as exc:
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

    while True:
        started = time.monotonic()
        db = SessionLocal()
        try:
            assets_scanned, opportunities_found, errors = run_scan_cycle(db, telegram_client)
            latency_ms = (time.monotonic() - started) * 1000
            emit_heartbeat(db, assets_scanned, opportunities_found, errors, latency_ms)
        except Exception:
            logger.exception("scan cycle failed")
        finally:
            db.close()

        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
