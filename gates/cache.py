#!/usr/bin/env python3
"""
Caching Layer for Phase 9 Performance Optimization

Implements LRU cache with TTL (Time-To-Live) for:
- HTML pages (60-minute TTL)
- API responses (5-minute TTL)
- Payment intent tokens (10-minute TTL)
- Nonce values (10-minute TTL)

Usage:
    from gates.cache import cached_http_get, cached_http_post, CacheStats
    
    # Simple GET with cache
    response = cached_http_get("https://example.com", cache_ttl=3600)
    
    # POST with cache
    response = cached_http_post("https://api.example.com", data={...}, cache_ttl=300)
    
    # View cache stats
    stats = CacheStats.get()
    print(f"Cache hit rate: {stats['hit_rate']:.1%}")
"""

import hashlib
import json
import time
from functools import wraps
from typing import Optional, Dict, Any, Callable
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests


@dataclass
class CacheEntry:
    """Single cache entry with TTL tracking"""
    key: str
    value: Any
    created_at: float
    ttl: int  # seconds
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        return time.time() - self.created_at > self.ttl


class LRUCacheWithTTL:
    """LRU Cache with Time-To-Live expiration"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
        }
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (returns None if expired or missing)"""
        if key not in self.cache:
            self.stats['misses'] += 1
            return None
        
        entry = self.cache[key]
        
        # Check expiration
        if entry.is_expired():
            del self.cache[key]
            self.stats['misses'] += 1
            return None
        
        # Move to end (LRU)
        self.cache.move_to_end(key)
        self.stats['hits'] += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache with TTL"""
        # Remove if exists (to update it)
        if key in self.cache:
            del self.cache[key]
        
        # Add new entry
        self.cache[key] = CacheEntry(key, value, time.time(), ttl)
        
        # Check size limit
        while len(self.cache) > self.max_size:
            removed_key = next(iter(self.cache))
            del self.cache[removed_key]
            self.stats['evictions'] += 1
        
        # Move to end
        self.cache.move_to_end(key)
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        self.stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
    def cleanup_expired(self) -> int:
        """Remove expired entries (returns count removed)"""
        expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)
    
    @property
    def size(self) -> int:
        """Current cache size"""
        return len(self.cache)
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)"""
        total = self.stats['hits'] + self.stats['misses']
        return self.stats['hits'] / total if total > 0 else 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.stats['hits'] + self.stats['misses']
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'evictions': self.stats['evictions'],
            'total_requests': total,
            'hit_rate': self.hit_rate,
        }


# Global cache instances
_html_cache = LRUCacheWithTTL(max_size=100)      # HTML pages
_api_cache = LRUCacheWithTTL(max_size=500)       # API responses
_token_cache = LRUCacheWithTTL(max_size=200)     # Tokens (short TTL)
_nonce_cache = LRUCacheWithTTL(max_size=200)     # Nonces (short TTL)


def _make_cache_key(url: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> str:
    """Create consistent cache key from URL and parameters"""
    key_parts = [url]
    
    if params:
        key_parts.append(json.dumps(params, sort_keys=True))
    if data:
        key_parts.append(json.dumps(data, sort_keys=True))
    
    key_str = '|'.join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def cached_http_get(
    url: str,
    params: Optional[Dict] = None,
    cache_ttl: int = 3600,
    cache_type: str = 'html',
    **kwargs
) -> Optional[requests.Response]:
    """
    GET request with caching
    
    Args:
        url: Request URL
        params: Query parameters
        cache_ttl: Cache TTL in seconds (default: 1 hour for HTML)
        cache_type: 'html', 'api', 'token', or 'nonce'
        **kwargs: Additional requests.get arguments
    
    Returns:
        Cached or fresh Response object
    """
    # Select cache instance
    cache = {
        'html': _html_cache,
        'api': _api_cache,
        'token': _token_cache,
        'nonce': _nonce_cache,
    }.get(cache_type, _html_cache)
    
    cache_key = _make_cache_key(url, params)
    
    # Try cache
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response
    
    # Fetch fresh
    try:
        response = requests.get(url, params=params, **kwargs)
        response.raise_for_status()
        cache.set(cache_key, response, ttl=cache_ttl)
        return response
    except Exception:
        return None


def cached_http_post(
    url: str,
    data: Optional[Dict] = None,
    json_data: Optional[Dict] = None,
    cache_ttl: int = 300,
    cache_type: str = 'api',
    **kwargs
) -> Optional[requests.Response]:
    """
    POST request with caching (use sparingly)
    
    Args:
        url: Request URL
        data: Form data
        json_data: JSON data
        cache_ttl: Cache TTL in seconds (default: 5 minutes)
        cache_type: 'html', 'api', 'token', or 'nonce'
        **kwargs: Additional requests.post arguments
    
    Returns:
        Cached or fresh Response object
    """
    # Select cache instance
    cache = {
        'html': _html_cache,
        'api': _api_cache,
        'token': _token_cache,
        'nonce': _nonce_cache,
    }.get(cache_type, _api_cache)
    
    cache_key = _make_cache_key(url, data=data or json_data)
    
    # Try cache
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response
    
    # Fetch fresh
    try:
        if json_data:
            response = requests.post(url, json=json_data, **kwargs)
        else:
            response = requests.post(url, data=data, **kwargs)
        response.raise_for_status()
        cache.set(cache_key, response, ttl=cache_ttl)
        return response
    except Exception:
        return None


def cache_result(ttl: int = 3600, cache_type: str = 'api'):
    """
    Decorator to cache function results
    
    Usage:
        @cache_result(ttl=300, cache_type='token')
        def get_payment_token(card_number):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Select cache
            cache = {
                'html': _html_cache,
                'api': _api_cache,
                'token': _token_cache,
                'nonce': _nonce_cache,
            }.get(cache_type, _api_cache)
            
            # Make key from function name and args
            key_parts = [func.__name__] + [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = hashlib.md5('|'.join(key_parts).encode()).hexdigest()
            
            # Try cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Call function
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result
        
        return wrapper
    return decorator


class CacheStats:
    """Global cache statistics"""
    
    @staticmethod
    def get() -> Dict[str, Any]:
        """Get all cache statistics"""
        return {
            'html_cache': _html_cache.get_stats(),
            'api_cache': _api_cache.get_stats(),
            'token_cache': _token_cache.get_stats(),
            'nonce_cache': _nonce_cache.get_stats(),
            'timestamp': datetime.now().isoformat(),
        }
    
    @staticmethod
    def clear_all() -> None:
        """Clear all caches"""
        _html_cache.clear()
        _api_cache.clear()
        _token_cache.clear()
        _nonce_cache.clear()
    
    @staticmethod
    def cleanup_expired() -> int:
        """Remove expired entries from all caches"""
        total = 0
        total += _html_cache.cleanup_expired()
        total += _api_cache.cleanup_expired()
        total += _token_cache.cleanup_expired()
        total += _nonce_cache.cleanup_expired()
        return total
    
    @staticmethod
    def print_stats() -> None:
        """Print formatted cache statistics"""
        stats = CacheStats.get()
        
        print("\n" + "="*80)
        print("CACHE STATISTICS")
        print("="*80)
        
        for cache_type, cache_stats in stats.items():
            if cache_type == 'timestamp':
                continue
            
            print(f"\n{cache_type.upper()}:")
            print(f"  Size:       {cache_stats['size']:4} / {cache_stats['max_size']:4} entries")
            print(f"  Hits:       {cache_stats['hits']:6} (hit rate: {cache_stats['hit_rate']:6.1%})")
            print(f"  Misses:     {cache_stats['misses']:6}")
            print(f"  Evictions:  {cache_stats['evictions']:6}")
        
        print("\n" + "="*80)


if __name__ == '__main__':
    # Test caching
    print("Testing Cache Implementation...")
    
    # Test 1: Simple caching
    @cache_result(ttl=10, cache_type='api')
    def slow_function(x):
        time.sleep(0.1)
        return x * 2
    
    # First call (should be slow)
    start = time.time()
    result1 = slow_function(5)
    elapsed1 = time.time() - start
    
    # Second call (should be fast from cache)
    start = time.time()
    result2 = slow_function(5)
    elapsed2 = time.time() - start
    
    print(f"First call:  {elapsed1:.3f}s (not cached)")
    print(f"Second call: {elapsed2:.3f}s (cached)")
    print(f"Speedup:     {elapsed1/elapsed2:.1f}x faster")
    
    # Print stats
    CacheStats.print_stats()
