import time
from typing import Any, Dict, Optional, Tuple

class AsyncTTLCache:
    """
    Asynchronous in-memory cache with Time-To-Live (TTL) expiration
    and simple capacity eviction (LRU-like fallback).
    """
    def __init__(self, max_size: int = 200, default_ttl_seconds: int = 600):
        self.max_size = max_size
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expire_at)

    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key. Returns None if key not found or expired."""
        if key not in self._cache:
            return None
            
        value, expire_at = self._cache[key]
        if time.time() > expire_at:
            # Evict expired entry
            self._cache.pop(key, None)
            return None
            
        return value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a value with a specific or default TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expire_at = time.time() + ttl
        
        # Eviction strategy if cache is saturated
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Find and evict any expired keys first
            now = time.time()
            expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
            if expired_keys:
                for ek in expired_keys:
                    self._cache.pop(ek, None)
            
            # Still saturated? Evict the oldest key in iteration order
            if len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key, None)
                
        self._cache[key] = (value, expire_at)

    async def invalidate(self, key: str) -> None:
        """Manually invalidate/delete a cached key."""
        self._cache.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys that start with the given prefix."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
        for k in keys_to_remove:
            self._cache.pop(k, None)

    async def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
