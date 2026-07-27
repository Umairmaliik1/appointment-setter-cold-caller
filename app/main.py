"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.repositories.campaign_repository import campaign_repository
from app.services.dialer_service import dialer_service
from app.services.redis_client import async_redis_client

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting Appointment-Setter-Cold-Caller")
    try:
        running = await campaign_repository.list_running_campaigns(limit=500)
        for campaign in running:
            await dialer_service.kick_campaign(
                campaign_id=campaign["id"],
                triggered_by="startup-recovery",
                reason="startup_recovery",
            )
    except Exception as exc:
        logger.warning("Startup recovery skipped: %s", exc)
    yield
    try:
        await async_redis_client.close()
    except Exception:
        logger.warning("Redis close failed during shutdown")


app = FastAPI(
    title="Appointment Setter Cold Caller API",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"service": "appointment-setter-cold-caller", "status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        proxy_headers=True,
    )
