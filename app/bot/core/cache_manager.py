#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Caching Layer with Redis
Provides optional Redis caching with local fallback
"""

import json
import logging
import os
import hashlib
from typing import Any, Optional, Callable
from functools import wraps
import time


class CacheManager:
    """
    Unified cache manager with Redis + local dict fallback
    """
    
    def __init__(self):
        self.redis_client = None
        self.local_cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
        self._init_redis()
    
    def _init_redis(self) -> None:
        """Initialize Redis connection if available"""
        redis_url = os.getenv('REDIS_URL')
        
        if not redis_url:
            logging.info("Redis URL not configured - using local cache only")
            return
        
        try:
            import redis
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            logging.info("✅ Redis connected successfully")
        except ImportError:
            logging.warning("redis package not installed - using local cache only. Install with: pip install redis")
        except Exception as e:
            logging.warning(f"Redis connection failed: {e} - using local cache only")
            self.redis_client = None
    
    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from prefix and arguments
        
        Args:
            prefix: Cache key prefix (e.g., 'product', 'faq')
            *args, **kwargs: Arguments to include in key
            
        Returns:
            Cache key string
        """
        # Serialize arguments
        key_parts = [str(arg) for arg in args]
        key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
        key_data = ":".join(key_parts)
        
        # Hash if too long
        if len(key_data) > 100:
            key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
            return f"{prefix}:{key_hash}"
        
        return f"{prefix}:{key_data}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        # Try Redis first
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value is not None:
                    self.cache_stats['hits'] += 1
                    return json.loads(value)
            except Exception as e:
                logging.warning(f"Redis GET error: {e}")
        
        # Fallback to local cache
        if key in self.local_cache:
            entry = self.local_cache[key]
            # Check expiry
            if entry['expires_at'] > time.time():
                self.cache_stats['hits'] += 1
                return entry['value']
            else:
                # Expired
                del self.local_cache[key]
        
        self.cache_stats['misses'] += 1
        return None
    
    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time to live in seconds (default: 5min)
            
        Returns:
            True if successful
        """
        try:
            # Try Redis first
            if self.redis_client:
                try:
                    serialized = json.dumps(value, ensure_ascii=False)
                    self.redis_client.setex(key, ttl, serialized)
                    self.cache_stats['sets'] += 1
                    return True
                except Exception as e:
                    logging.warning(f"Redis SET error: {e}")
            
            # Fallback to local cache
            self.local_cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl
            }
            self.cache_stats['sets'] += 1
            
            # Limit local cache size
            if len(self.local_cache) > 1000:
                # Remove oldest entries
                sorted_keys = sorted(
                    self.local_cache.keys(),
                    key=lambda k: self.local_cache[k]['expires_at']
                )
                for k in sorted_keys[:200]:
                    del self.local_cache[k]
            
            return True
            
        except Exception as e:
            logging.error(f"Cache SET error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            
            if key in self.local_cache:
                del self.local_cache[key]
            
            self.cache_stats['deletes'] += 1
            return True
        except Exception as e:
            logging.error(f"Cache DELETE error: {e}")
            return False
    
    def clear_prefix(self, prefix: str) -> int:
        """
        Clear all keys with given prefix
        
        Args:
            prefix: Key prefix to clear
            
        Returns:
            Number of keys deleted
        """
        count = 0
        
        # Redis
        if self.redis_client:
            try:
                keys = self.redis_client.keys(f"{prefix}:*")
                if keys:
                    count = self.redis_client.delete(*keys)
            except Exception as e:
                logging.error(f"Redis clear error: {e}")
        
        # Local cache
        keys_to_delete = [k for k in self.local_cache.keys() if k.startswith(f"{prefix}:")]
        for k in keys_to_delete:
            del self.local_cache[k]
            count += 1
        
        return count
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.cache_stats,
            'hit_rate': f"{hit_rate:.1f}%",
            'using_redis': self.redis_client is not None,
            'local_cache_size': len(self.local_cache)
        }


# Global cache instance
_cache = None


def get_cache() -> CacheManager:
    """Get or create global cache instance"""
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


def cached(prefix: str, ttl: int = 300):
    """
    Decorator to cache function results
    
    Usage:
        @cached('products', ttl=600)
        def get_products():
            return expensive_db_query()
    
    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Generate cache key
            cache_key = cache._make_key(prefix, *args, **kwargs)
            
            # Try cache first
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logging.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Cache miss - call function
            logging.debug(f"Cache MISS: {cache_key}")
            result = func(*args, **kwargs)
            
            # Cache result
            cache.set(cache_key, result, ttl=ttl)
            
            return result
        
        return wrapper
    return decorator


def invalidate_cache(prefix: str) -> int:
    """
    Invalidate all cached values with given prefix
    
    Usage:
        invalidate_cache('products')  # Clear all product caches
    
    Args:
        prefix: Cache key prefix to invalidate
        
    Returns:
        Number of keys invalidated
    """
    cache = get_cache()
    return cache.clear_prefix(prefix)
