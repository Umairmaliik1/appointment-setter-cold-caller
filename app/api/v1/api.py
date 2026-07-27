"""API router aggregation."""

from fastapi import APIRouter

from app.api.v1.routers import campaigns, dnc, health, twilio

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(campaigns.router)
api_router.include_router(dnc.router)
api_router.include_router(twilio.router)

