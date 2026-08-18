"""
ALPHAQUANT X — API

DON'T CHASE TRADES. FIND QUALITY.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alphaquant_core.core.config import get_settings
from app.routers import backtests, health, market_data, opportunities, playbooks, summary, webhooks

settings = get_settings()

app = FastAPI(
    title="AlphaQuant X API",
    description="Market Intelligence & Trade Scanner",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir ao domínio do dashboard em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(market_data.router)
app.include_router(opportunities.router)
app.include_router(playbooks.router)
app.include_router(summary.router)
app.include_router(backtests.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "ALPHAQUANT X",
        "tagline": "DON'T CHASE TRADES. FIND QUALITY.",
        "environment": settings.ENVIRONMENT,
        "test_mode": settings.TEST_MODE,
    }
