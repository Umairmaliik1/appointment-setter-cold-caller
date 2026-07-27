"""Async Redis client wrapper."""

import json
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import settings


class AsyncRedisClient:
    def __init__(self) -> None:
        self._client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def set_json(self, key: str, value: dict, ttl: Optional[int] = None) -> None:
        payload = json.dumps(value)
        if ttl:
            await self._client.set(key, payload, ex=ttl)
            return
        await self._client.set(key, payload)

    async def get_json(self, key: str) -> Optional[dict]:
        raw = await self._client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def close(self) -> None:
        await self._client.aclose()


async_redis_client = AsyncRedisClient()

