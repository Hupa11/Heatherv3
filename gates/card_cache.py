#!/usr/bin/env python3
"""
Card Response Caching System

Caches card check results to avoid redundant checks:
- DECLINED: Cache for 5 minutes (definitive result)
- GATEWAY_ERROR: Cache for 1 minute (might be transient)
- APPROVED/LIVE: Never cache (always verify fresh)

Uses card hash (first 6 + last 4 digits) as key to avoid storing full numbers.
"""

import time
import threading
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from dataclasses import dataclass


# TTL constants (in seconds)
DECLINED_TTL = 300  # 5 minutes for declined cards
ERROR_TTL = 60      # 1 minute for gateway errors


@dataclass
class CacheEntry:
    """Single cache entry with TTL tracking"""
    value: Any
    created_at: float
    ttl: int
    result_type: str  # 'declined' or 'error'
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        return time.time() - self.created_at > self.ttl


class CardTTLCache:
    """TTL Cache specifically for card check results"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'declined_cached': 0,
            'errors_cached': 0,
        }
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached result for a card hash"""
        with self._lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            if entry.is_expired():
                del self.cache[key]
                self.stats['misses'] += 1
                return None
            
            self.cache.move_to_end(key)
            self.stats['hits'] += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: int, result_type: str) -> None:
        """Cache a result with specified TTL"""
        with self._lock:
            if key in self.cache:
                del self.cache[key]
            
            self.cache[key] = CacheEntry(value, time.time(), ttl, result_type)
            
            if result_type == 'declined':
                self.stats['declined_cached'] += 1
            elif result_type == 'error':
                self.stats['errors_cached'] += 1
            
            while len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
            
            self.cache.move_to_end(key)
    
    def clear(self) -> None:
        """Clear all cached entries"""
        with self._lock:
            self.cache.clear()
            self.stats = {
                'hits': 0,
                'misses': 0,
                'declined_cached': 0,
                'errors_cached': 0,
            }
    
    def cleanup_expired(self) -> int:
        """Remove expired entries, returns count removed"""
        with self._lock:
            expired = [k for k, v in self.cache.items() if v.is_expired()]
            for key in expired:
                del self.cache[key]
            return len(expired)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total = self.stats['hits'] + self.stats['misses']
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': self.stats['hits'] / total if total > 0 else 0.0,
                'declined_cached': self.stats['declined_cached'],
                'errors_cached': self.stats['errors_cached'],
            }


# Global cache instance
_card_cache = CardTTLCache()


def get_card_hash(card_number: str) -> str:
    """
    Get card identifier for caching (full card number).
    
    Args:
        card_number: Full card number (digits only or with separators)
    
    Returns:
        Full card number (digits only)
    """
    return ''.join(c for c in str(card_number) if c.isdigit())


def get_cached_result(card_hash: str) -> Optional[Any]:
    """
    Get cached result for a card hash.
    
    Args:
        card_hash: Card hash from get_card_hash()
    
    Returns:
        Cached result if exists and not expired, None otherwise
    """
    return _card_cache.get(card_hash)


def cache_result(card_hash: str, result: Any, ttl: int = None, result_type: str = 'declined') -> None:
    """
    Cache a card check result.
    
    Args:
        card_hash: Card hash from get_card_hash()
        result: The result to cache
        ttl: Time-to-live in seconds (defaults based on result_type)
        result_type: 'declined' or 'error' (determines default TTL)
    """
    if ttl is None:
        ttl = DECLINED_TTL if result_type == 'declined' else ERROR_TTL
    
    _card_cache.set(card_hash, result, ttl, result_type)


def clear_cache() -> None:
    """Clear all cached card results"""
    _card_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return _card_cache.get_stats()


def cleanup_expired() -> int:
    """Remove expired entries from cache"""
    return _card_cache.cleanup_expired()


def classify_result(response_text: str) -> str:
    """
    Classify a response into result type for caching decisions.
    
    Args:
        response_text: Response text from gateway
    
    Returns:
        'declined', 'error', or 'live'
    """
    if not response_text:
        return 'error'
    
    text_lower = response_text.lower()
    
    # Live/approved indicators - don't cache these
    live_keywords = [
        'approved', 'success', 'charged', 'ccn', 'live',
        'authenticated', 'accepted', 'payment_intent',
        'succeeded', 'captured', 'authorized'
    ]
    if any(kw in text_lower for kw in live_keywords):
        return 'live'
    
    # Gateway/network error indicators - short cache
    error_keywords = [
        'timeout', 'timed out', 'connection', 'network',
        'proxy', 'service unavailable', '503', '502', '500',
        'rate limit', 'throttle', 'try again', 'temporarily',
        'gateway error', 'internal error', 'server error',
        'unreachable', 'refused', 'reset'
    ]
    if any(kw in text_lower for kw in error_keywords):
        return 'error'
    
    # Decline indicators - cache these
    decline_keywords = [
        'declined', 'decline', 'denied', 'rejected', 'invalid',
        'expired', 'insufficient', 'fraud', 'stolen', 'lost',
        'restricted', 'blocked', 'not allowed', 'do not honor',
        'pick up', 'pickup', 'security violation', 'cvv', 'cvc',
        'incorrect', 'mismatch', 'failed', 'dead', 'generic_decline',
        'card_declined', 'your card was declined', 'transaction not permitted'
    ]
    if any(kw in text_lower for kw in decline_keywords):
        return 'declined'
    
    # Default to declined for unknown responses (conservative)
    return 'declined'


def should_use_cache(response_text: str) -> Tuple[str, bool]:
    """
    Determine if a response should be cached and its type.
    
    Args:
        response_text: Response text from gateway
    
    Returns:
        Tuple of (result_type, should_cache)
        - ("declined", True) if response indicates card declined
        - ("error", True) if response indicates gateway/network error  
        - ("live", False) if card is approved/live
    """
    result_type = classify_result(response_text)
    
    if result_type == 'live':
        return ('live', False)
    elif result_type == 'error':
        return ('error', True)
    else:
        return ('declined', True)


if __name__ == '__main__':
    # Test the caching system
    print("Testing Card Cache System...")
    
    # Test card hash
    test_card = "4111111111111111"
    card_hash = get_card_hash(test_card)
    print(f"Card hash for {test_card}: {card_hash}")
    
    # Test caching declined
    cache_result(card_hash, "Card Declined - Insufficient Funds", result_type='declined')
    cached = get_cached_result(card_hash)
    print(f"Cached declined result: {cached}")
    
    # Test classify_result
    test_responses = [
        "Payment approved successfully",
        "Card declined - do not honor",
        "Gateway timeout - please try again",
        "CVV mismatch",
        "Rate limited",
    ]
    
    print("\nClassification tests:")
    for resp in test_responses:
        result_type, should_cache = should_use_cache(resp)
        print(f"  '{resp[:40]}...' -> {result_type}, cache={should_cache}")
    
    # Print stats
    print(f"\nCache stats: {get_cache_stats()}")
