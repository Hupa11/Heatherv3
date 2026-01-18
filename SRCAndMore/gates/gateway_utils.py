"""
Gateway Utilities - Unified interface for all gateway improvements
Integrates stealth, circuit breaker, response parsing, and connection pooling
"""

import time
import random
from typing import Tuple, Optional, Dict, Any, Callable
from functools import wraps

from gates.stealth import (
    StealthSession, 
    get_random_headers, 
    random_delay,
    get_stripe_headers,
    get_braintree_headers,
    get_paypal_headers,
)
from gates.circuit_breaker import (
    is_gateway_available,
    record_gateway_success,
    record_gateway_failure,
    get_gateway_status_report,
    with_circuit_breaker,
    is_infrastructure_failure,
)
from gates.response_parser import (
    ParsedResponse,
    CardStatus,
    parse_stripe_response,
    parse_paypal_response,
    parse_braintree_response,
    parse_generic_response,
    auto_parse_response,
)
from gates.retry import RetryConfig, retry_with_backoff


# Token/key cache with TTL
_token_cache: Dict[str, Tuple[Any, float]] = {}
_cache_ttl = 300  # 5 minutes default


def cache_token(key: str, value: Any, ttl: Optional[float] = None) -> None:
    """Cache a token or key with expiration"""
    _token_cache[key] = (value, time.time() + (ttl or _cache_ttl))


def get_cached_token(key: str) -> Optional[Any]:
    """Get a cached token if not expired"""
    if key in _token_cache:
        value, expires = _token_cache[key]
        if time.time() < expires:
            return value
        del _token_cache[key]
    return None


def clear_token_cache() -> None:
    """Clear all cached tokens"""
    _token_cache.clear()


class NetworkError(Exception):
    """Raised for network/connection errors - these count as circuit breaker failures"""
    pass


class CardDeclineError(Exception):
    """Raised for card declines - these do NOT count as circuit breaker failures"""
    pass


class GatewaySession:
    """
    Enhanced session for gateway requests with integrated stealth and tracking.
    
    Distinguishes between:
    - Network errors (timeout, connection) -> triggers circuit breaker
    - Card declines -> does NOT trigger circuit breaker
    """
    
    def __init__(self, gateway_name: str, proxy: Optional[str] = None):
        self.gateway_name = gateway_name
        self.proxy = proxy
        self.stealth = StealthSession()
        self.request_count = 0
        self.success_count = 0
        self.network_failure_count = 0
        self.card_decline_count = 0
        self.last_error: Optional[str] = None
        self.last_error_type: Optional[str] = None  # 'network' or 'card'
        
        # Import requests here to avoid circular imports
        import requests
        self.session = requests.Session()
        self.session.verify = False
        
        if proxy:
            self._setup_proxy(proxy)
    
    def _setup_proxy(self, proxy: str) -> None:
        """Configure proxy from various formats"""
        if "://" in proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        elif proxy.count(":") == 3:
            # host:port:user:pass format
            parts = proxy.split(":")
            proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        else:
            # host:port format
            self.session.proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    
    def get(self, url: str, **kwargs) -> 'requests.Response':
        """Make GET request with stealth headers"""
        return self._request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> 'requests.Response':
        """Make POST request with stealth headers"""
        return self._request("POST", url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> 'requests.Response':
        """
        Internal request method with stealth and tracking.
        
        Raises:
            CircuitOpenError: If circuit breaker is open
            NetworkError: For timeout/connection errors (triggers circuit breaker)
        
        Returns:
            Response object (even for HTTP 4xx/5xx - these are not network errors)
        """
        import requests
        
        # Check circuit breaker first
        if not is_gateway_available(self.gateway_name):
            raise CircuitOpenError(f"Gateway {self.gateway_name} circuit is open")
        
        # Add delay if configured
        self.stealth.pre_request_delay()
        
        # Build headers
        referer = kwargs.pop("referer", None)
        origin = kwargs.pop("origin", None)
        api_mode = bool(kwargs.get("data") or kwargs.get("json"))
        
        headers = self.stealth.get_headers(referer=referer, origin=origin, api_mode=api_mode)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        kwargs["headers"] = headers
        
        try:
            response = self.session.request(method, url, **kwargs)
            self.stealth.post_request()
            self.request_count += 1
            
            # HTTP responses (even 4xx/5xx) are NOT network errors
            # The gateway responded, even if the card was declined
            return response
            
        except requests.exceptions.Timeout as e:
            self.network_failure_count += 1
            self.last_error = f"Timeout: {str(e)}"
            self.last_error_type = 'network'
            record_gateway_failure(self.gateway_name)
            raise NetworkError(f"Request timed out: {str(e)}") from e
            
        except requests.exceptions.ConnectionError as e:
            self.network_failure_count += 1
            self.last_error = f"Connection error: {str(e)}"
            self.last_error_type = 'network'
            record_gateway_failure(self.gateway_name)
            raise NetworkError(f"Connection failed: {str(e)}") from e
            
        except requests.exceptions.SSLError as e:
            self.network_failure_count += 1
            self.last_error = f"SSL error: {str(e)}"
            self.last_error_type = 'network'
            record_gateway_failure(self.gateway_name)
            raise NetworkError(f"SSL error: {str(e)}") from e
            
        except requests.exceptions.ProxyError as e:
            self.network_failure_count += 1
            self.last_error = f"Proxy error: {str(e)}"
            self.last_error_type = 'network'
            record_gateway_failure(self.gateway_name)
            raise NetworkError(f"Proxy failed: {str(e)}") from e
    
    def record_result(self, parsed: ParsedResponse) -> None:
        """
        Record result for circuit breaker tracking.
        
        Only infrastructure failures (timeout, rate limit, gateway error) trigger
        circuit breaker. Card declines are treated as successful gateway operations.
        """
        if parsed.status in [CardStatus.TIMEOUT, CardStatus.RATE_LIMITED]:
            # Infrastructure failures
            self.network_failure_count += 1
            record_gateway_failure(self.gateway_name)
        elif parsed.status == CardStatus.ERROR:
            # Check if it's a gateway error vs card error
            if parsed.decline_code and any(kw in parsed.decline_code.lower() 
                for kw in ["timeout", "connection", "network", "rate"]):
                self.network_failure_count += 1
                record_gateway_failure(self.gateway_name)
            else:
                # Likely a card-related error, not infrastructure
                self.card_decline_count += 1
                record_gateway_success(self.gateway_name)
        else:
            # All card responses (LIVE, CCN, DECLINED, CVV, etc.) are gateway successes
            if parsed.is_live or parsed.is_ccn:
                self.success_count += 1
            else:
                self.card_decline_count += 1
            record_gateway_success(self.gateway_name)
    
    def record_network_error(self, error: str) -> None:
        """Explicitly record a network error for circuit breaker"""
        self.network_failure_count += 1
        self.last_error = error
        self.last_error_type = 'network'
        record_gateway_failure(self.gateway_name)
    
    def record_card_response(self, is_success: bool = False) -> None:
        """Record a card response (success or decline) - not a circuit breaker failure"""
        if is_success:
            self.success_count += 1
        else:
            self.card_decline_count += 1
        record_gateway_success(self.gateway_name)


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


def enhanced_gateway(gateway_name: str):
    """
    Decorator to add all enhancements to a gateway function.
    
    Adds:
    - Circuit breaker protection (only for infrastructure failures)
    - Response parsing and normalization
    - Request timing jitter
    
    IMPORTANT: Only counts infrastructure failures (timeout, connection errors)
    as circuit breaker failures. Card declines are NOT failures.
    
    Usage:
        @enhanced_gateway("stripe_auth")
        def stripe_auth_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
            ...
            return result_string, proxy_ok
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Tuple[str, bool]:
            # Check circuit breaker
            if not is_gateway_available(gateway_name):
                return (f"[CIRCUIT OPEN] {gateway_name} temporarily disabled", False)
            
            # Add pre-request jitter
            random_delay(min_seconds=0.1, max_seconds=0.5)
            
            try:
                result = func(*args, **kwargs)
                
                if isinstance(result, tuple) and len(result) >= 2:
                    status_msg, proxy_ok = result[0], result[1]
                    
                    # Use the refined infrastructure failure check
                    # Only network/infrastructure issues trigger circuit breaker
                    if is_infrastructure_failure(status_msg, proxy_ok):
                        record_gateway_failure(gateway_name)
                    else:
                        # Card responses (including declines) are gateway successes
                        record_gateway_success(gateway_name)
                    
                    # Parse response for enhanced display
                    parsed = auto_parse_response(status_msg, gateway_name)
                    
                    # Return enhanced status if confidence is high
                    if parsed.confidence >= 0.8:
                        return (parsed.to_display(), proxy_ok)
                    
                    return result
                else:
                    record_gateway_success(gateway_name)
                    return result
                    
            except (NetworkError, CircuitOpenError) as e:
                # Network-level errors trigger circuit breaker
                record_gateway_failure(gateway_name)
                return (f"⚠️ Network Error: {str(e)[:40]}", False)
                
            except Exception as e:
                # Other exceptions - check if it looks like network error
                error_str = str(e).lower()
                if any(kw in error_str for kw in ["timeout", "connection", "socket", "ssl", "proxy"]):
                    record_gateway_failure(gateway_name)
                    return (f"⚠️ Network Error: {str(e)[:40]}", False)
                else:
                    # Unknown exception - don't trip circuit breaker
                    record_gateway_success(gateway_name)
                    return (f"Error: {str(e)[:50]}", True)
        
        return wrapper
    return decorator


def format_result(
    status: CardStatus,
    card_num: str,
    bin_info: Optional[Dict] = None,
    extra: Optional[str] = None
) -> str:
    """Format a standardized result string"""
    emoji = {
        CardStatus.LIVE: "✅",
        CardStatus.CCN: "🔵",
        CardStatus.CVV_MISMATCH: "⚠️",
        CardStatus.INSUFFICIENT: "💰",
        CardStatus.EXPIRED: "📅",
        CardStatus.THREE_DS: "🔐",
        CardStatus.DECLINED: "❌",
        CardStatus.ERROR: "⚠️",
    }.get(status, "❓")
    
    status_text = {
        CardStatus.LIVE: "APPROVED",
        CardStatus.CCN: "CCN",
        CardStatus.CVV_MISMATCH: "CVV Mismatch",
        CardStatus.INSUFFICIENT: "Insufficient Funds",
        CardStatus.EXPIRED: "Expired",
        CardStatus.THREE_DS: "3D Secure",
        CardStatus.DECLINED: "DECLINED",
        CardStatus.ERROR: "Error",
    }.get(status, "Unknown")
    
    result = f"{emoji} {status_text}"
    
    if bin_info:
        bin_str = bin_info.get("formatted", "")
        if bin_str:
            result += f" ({bin_str})"
    
    if extra:
        result += f" - {extra}"
    
    return result


def with_retry(
    func: Callable,
    max_retries: int = 2,
    base_delay: float = 1.0,
) -> Callable:
    """
    Wrap a function with retry logic.
    
    Args:
        func: Function to wrap
        max_retries: Maximum retry attempts
        base_delay: Base delay between retries
    
    Returns:
        Wrapped function with retry logic
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=10.0,
        jitter=0.2,
    )
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        return retry_with_backoff(func, args, kwargs, config=config)
    
    return wrapper


# Convenience exports
__all__ = [
    # Session management
    'GatewaySession',
    'CircuitOpenError',
    'NetworkError',
    'CardDeclineError',
    
    # Decorators
    'enhanced_gateway',
    'with_retry',
    'with_circuit_breaker',
    
    # Caching
    'cache_token',
    'get_cached_token',
    'clear_token_cache',
    
    # Headers
    'get_random_headers',
    'get_stripe_headers',
    'get_braintree_headers',
    'get_paypal_headers',
    
    # Response parsing
    'ParsedResponse',
    'CardStatus',
    'parse_stripe_response',
    'parse_paypal_response',
    'parse_braintree_response',
    'parse_generic_response',
    'auto_parse_response',
    
    # Circuit breaker helpers
    'is_infrastructure_failure',
    
    # Utilities
    'random_delay',
    'format_result',
    'get_gateway_status_report',
]
