"""Redis cache client for session caching and rate limiting."""

import json
import os
from typing import Any, Optional

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from aws_lambda_powertools import Logger

logger = Logger()


class RedisCache:
    """Redis cache client with connection pooling."""

    _instance: Optional["RedisCache"] = None
    _redis_client: Any = None

    def __new__(cls) -> "RedisCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available, caching disabled")
            return

        if self._redis_client is None:
            self._connect()

    def _connect(self) -> None:
        """Establish Redis connection."""
        if not REDIS_AVAILABLE:
            return

        try:
            self._redis_client = redis.Redis(
                host=os.environ.get("REDIS_ENDPOINT", ""),
                port=int(os.environ.get("REDIS_PORT", "6379")),
                password=os.environ.get("REDIS_AUTH_TOKEN", ""),
                ssl=True,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            self._redis_client.ping()
            logger.info("Redis connection established")
        except Exception:
            logger.exception("Failed to connect to Redis")
            self._redis_client = None

    def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self._redis_client:
            return None

        try:
            value = self._redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis GET error: {str(e)}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_client:
            return False

        try:
            serialized = json.dumps(value, default=str)
            self._redis_client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {str(e)}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_client:
            return False

        try:
            self._redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error: {str(e)}")
            return False

    def increment(self, key: str, amount: int = 1, ttl: int | None = None) -> int | None:
        """
        Increment counter (for rate limiting).

        Args:
            key: Counter key
            amount: Amount to increment
            ttl: Time to live for new counters

        Returns:
            New counter value or None on error
        """
        if not self._redis_client:
            return None

        try:
            value = self._redis_client.incr(key, amount)
            if ttl and value == amount:  # First increment, set TTL
                self._redis_client.expire(key, ttl)
            return value
        except Exception as e:
            logger.error(f"Redis INCR error: {str(e)}")
            return None


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, cache: RedisCache) -> None:
        self.cache = cache

    def is_allowed(
        self, identifier: str, max_requests: int = 100, window_seconds: int = 60
    ) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: User ID, IP, or API key
            max_requests: Maximum requests in window
            window_seconds: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        key = f"ratelimit:{identifier}"
        current_count = self.cache.increment(key, ttl=window_seconds)

        if current_count is None:
            # Cache unavailable, allow request (fail open)
            logger.warning("Rate limiter cache unavailable, allowing request")
            return True

        allowed = current_count <= max_requests

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "identifier": identifier,
                    "count": current_count,
                    "limit": max_requests,
                },
            )

        return allowed
