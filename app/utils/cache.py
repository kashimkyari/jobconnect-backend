import redis.asyncio as redis
from ..config import settings

redis_client = redis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)

async def get_cache(key: str):
    return await redis_client.get(key)

async def set_cache(key: str, value: str, expire: int = 3600):
    await redis_client.set(key, value, ex=expire)

async def delete_cache(key: str):
    await redis_client.delete(key)


async def delete_cache_by_prefix(prefix: str):
    keys = [key async for key in redis_client.scan_iter(f"{prefix}*")]
    if keys:
        await redis_client.delete(*keys)
