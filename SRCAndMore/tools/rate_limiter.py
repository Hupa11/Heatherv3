"""
Rate Limiter - Per-site request throttling with adaptive backoff.

Features:
- Per-domain rate limiting with configurable requests/second
- Adaptive backoff on rate limit responses (429, 503)
- Automatic cooldown periods after hitting limits
- Thread-safe for concurrent usage
- Site-specific configuration overrides
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitConfig:
    """Configuration for a specific domain's rate limiting."""
    requests_per_second: float = 2.0
    burst_limit: int = 5
    cooldown_seconds: float = 30.0
    max_backoff_seconds: float = 300.0
    backoff_multiplier: float = 2.0


@dataclass
class DomainState:
    """Tracks rate limiting state for a domain."""
    last_request_time: float = 0.0
    request_count: int = 0
    window_start: float = 0.0
    backoff_until: float = 0.0
    current_backoff: float = 0.0
    consecutive_limits: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class RateLimiter:
    """
    Thread-safe rate limiter with per-domain tracking and adaptive backoff.
    
    Usage:
        limiter = RateLimiter()
        
        # Wait for rate limit before making request
        limiter.wait_if_needed("example.com")
        response = requests.get("https://example.com/api")
        
        # Report rate limit hit for adaptive backoff
        if response.status_code == 429:
            limiter.report_rate_limit("example.com")
    """
    
    DEFAULT_CONFIG = RateLimitConfig()
    
    SITE_CONFIGS = {
        "shopify.com": RateLimitConfig(requests_per_second=1.0, burst_limit=3, cooldown_seconds=60.0),
        "stripe.com": RateLimitConfig(requests_per_second=5.0, burst_limit=10, cooldown_seconds=30.0),
        "paypal.com": RateLimitConfig(requests_per_second=2.0, burst_limit=5, cooldown_seconds=45.0),
        "braintreegateway.com": RateLimitConfig(requests_per_second=3.0, burst_limit=5, cooldown_seconds=30.0),
    }
    
    def __init__(self):
        self._domains: dict[str, DomainState] = defaultdict(DomainState)
        self._global_lock = threading.Lock()
    
    def _get_config(self, domain: str) -> RateLimitConfig:
        """Get rate limit config for domain, checking for known patterns."""
        domain_lower = domain.lower()
        
        for pattern, config in self.SITE_CONFIGS.items():
            if pattern in domain_lower:
                return config
        
        return self.DEFAULT_CONFIG
    
    def _get_domain_state(self, domain: str) -> DomainState:
        """Get or create domain state with thread safety."""
        with self._global_lock:
            if domain not in self._domains:
                self._domains[domain] = DomainState()
            return self._domains[domain]
    
    def _extract_domain(self, url_or_domain: str) -> str:
        """Extract domain from URL or return as-is if already a domain."""
        if "://" in url_or_domain:
            from urllib.parse import urlparse
            parsed = urlparse(url_or_domain)
            return parsed.netloc or url_or_domain
        return url_or_domain
    
    def wait_if_needed(self, url_or_domain: str, timeout: float = 60.0) -> float:
        """
        Wait if rate limit would be exceeded. Returns time waited.
        
        Args:
            url_or_domain: URL or domain to check rate limit for
            timeout: Maximum time to wait (seconds)
            
        Returns:
            Time waited in seconds (0 if no wait needed)
        """
        domain = self._extract_domain(url_or_domain)
        config = self._get_config(domain)
        state = self._get_domain_state(domain)
        
        waited = 0.0
        
        with state.lock:
            now = time.time()
            
            if now < state.backoff_until:
                wait_time = min(state.backoff_until - now, timeout)
                if wait_time > 0:
                    time.sleep(wait_time)
                    waited += wait_time
                    now = time.time()
            
            if now - state.window_start >= 1.0:
                state.window_start = now
                state.request_count = 0
            
            if state.request_count >= config.burst_limit:
                wait_time = min(1.0 - (now - state.window_start), timeout - waited)
                if wait_time > 0:
                    time.sleep(wait_time)
                    waited += wait_time
                    now = time.time()
                state.window_start = now
                state.request_count = 0
            
            min_interval = 1.0 / config.requests_per_second
            time_since_last = now - state.last_request_time
            
            if time_since_last < min_interval:
                wait_time = min(min_interval - time_since_last, timeout - waited)
                if wait_time > 0:
                    time.sleep(wait_time)
                    waited += wait_time
            
            state.last_request_time = time.time()
            state.request_count += 1
        
        return waited
    
    def report_rate_limit(self, url_or_domain: str, status_code: int = 429) -> float:
        """
        Report that a rate limit was hit. Applies adaptive backoff.
        
        Args:
            url_or_domain: URL or domain that returned rate limit
            status_code: HTTP status code (429, 503, etc.)
            
        Returns:
            Backoff time in seconds
        """
        domain = self._extract_domain(url_or_domain)
        config = self._get_config(domain)
        state = self._get_domain_state(domain)
        
        with state.lock:
            state.consecutive_limits += 1
            
            if state.current_backoff == 0:
                state.current_backoff = config.cooldown_seconds
            else:
                state.current_backoff = min(
                    state.current_backoff * config.backoff_multiplier,
                    config.max_backoff_seconds
                )
            
            if status_code == 503:
                state.current_backoff = min(state.current_backoff * 1.5, config.max_backoff_seconds)
            
            state.backoff_until = time.time() + state.current_backoff
            
            return state.current_backoff
    
    def report_success(self, url_or_domain: str) -> None:
        """Report successful request - reduces backoff over time."""
        domain = self._extract_domain(url_or_domain)
        state = self._get_domain_state(domain)
        
        with state.lock:
            state.consecutive_limits = 0
            if state.current_backoff > 0:
                state.current_backoff = state.current_backoff * 0.9
                if state.current_backoff < 1.0:
                    state.current_backoff = 0.0
    
    def get_status(self, url_or_domain: str) -> dict:
        """Get current rate limit status for a domain."""
        domain = self._extract_domain(url_or_domain)
        config = self._get_config(domain)
        state = self._get_domain_state(domain)
        
        now = time.time()
        
        with state.lock:
            return {
                "domain": domain,
                "requests_per_second": config.requests_per_second,
                "burst_limit": config.burst_limit,
                "current_count": state.request_count,
                "in_backoff": now < state.backoff_until,
                "backoff_remaining": max(0, state.backoff_until - now),
                "consecutive_limits": state.consecutive_limits,
            }
    
    def reset(self, url_or_domain: Optional[str] = None) -> None:
        """Reset rate limit state for a domain or all domains."""
        if url_or_domain:
            domain = self._extract_domain(url_or_domain)
            with self._global_lock:
                if domain in self._domains:
                    del self._domains[domain]
        else:
            with self._global_lock:
                self._domains.clear()


_global_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter()
    return _global_limiter


def wait_for_rate_limit(url_or_domain: str, timeout: float = 60.0) -> float:
    """Convenience function to wait for rate limit using global limiter."""
    return get_rate_limiter().wait_if_needed(url_or_domain, timeout)


def report_rate_limit_hit(url_or_domain: str, status_code: int = 429) -> float:
    """Convenience function to report rate limit hit using global limiter."""
    return get_rate_limiter().report_rate_limit(url_or_domain, status_code)


def report_request_success(url_or_domain: str) -> None:
    """Convenience function to report successful request using global limiter."""
    get_rate_limiter().report_success(url_or_domain)
