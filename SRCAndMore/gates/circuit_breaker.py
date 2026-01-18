"""
Circuit Breaker Pattern for Gateway Resilience
Auto-disables failing gateways temporarily to prevent cascade failures
"""

import time
import threading
from typing import Dict, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for a single gateway.
    
    States:
    - CLOSED: Normal operation. Track failures. Open if threshold exceeded.
    - OPEN: All requests fail fast. After timeout, move to HALF_OPEN.
    - HALF_OPEN: Allow one test request. If success -> CLOSED. If fail -> OPEN.
    """
    name: str
    failure_threshold: int = 5          # Consecutive failures before opening
    success_threshold: int = 2          # Consecutive successes to close from half-open
    timeout_seconds: float = 60.0       # Time to wait before trying again
    
    # State tracking
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0
    
    # Statistics
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    times_opened: int = 0
    
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def is_available(self) -> bool:
        """Check if circuit allows requests"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                # Check if timeout has passed
                if time.time() - self.opened_at >= self.timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    return True
                return False
            
            # HALF_OPEN - allow limited requests
            return True
    
    def record_success(self) -> None:
        """Record a successful request"""
        with self._lock:
            self.total_requests += 1
            self.total_successes += 1
            self.last_success_time = time.time()
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
            elif self.state == CircuitState.CLOSED:
                pass  # Normal operation
    
    def record_failure(self) -> None:
        """Record a failed request"""
        with self._lock:
            self.total_requests += 1
            self.total_failures += 1
            self.last_failure_time = time.time()
            self.failure_count += 1
            
            if self.state == CircuitState.HALF_OPEN:
                # Immediate return to OPEN on any failure
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
                self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.opened_at = time.time()
                    self.times_opened += 1
                    self.failure_count = 0
    
    def get_status(self) -> Dict:
        """Get current circuit status"""
        with self._lock:
            success_rate = 0.0
            if self.total_requests > 0:
                success_rate = self.total_successes / self.total_requests
            
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "total_requests": self.total_requests,
                "success_rate": round(success_rate * 100, 1),
                "times_opened": self.times_opened,
                "time_until_retry": max(0, self.timeout_seconds - (time.time() - self.opened_at)) if self.state == CircuitState.OPEN else 0,
            }
    
    def reset(self) -> None:
        """Reset circuit to initial state"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0


class CircuitBreakerRegistry:
    """
    Registry to manage circuit breakers for all gateways.
    """
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        
        # Default settings
        self.default_failure_threshold = 5
        self.default_success_threshold = 2
        self.default_timeout = 60.0
    
    def get_or_create(self, gateway_name: str, 
                      failure_threshold: Optional[int] = None,
                      success_threshold: Optional[int] = None,
                      timeout_seconds: Optional[float] = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a gateway"""
        with self._lock:
            if gateway_name not in self._breakers:
                self._breakers[gateway_name] = CircuitBreaker(
                    name=gateway_name,
                    failure_threshold=failure_threshold or self.default_failure_threshold,
                    success_threshold=success_threshold or self.default_success_threshold,
                    timeout_seconds=timeout_seconds or self.default_timeout,
                )
            return self._breakers[gateway_name]
    
    def is_available(self, gateway_name: str) -> bool:
        """Check if a gateway is available"""
        breaker = self.get_or_create(gateway_name)
        return breaker.is_available()
    
    def record_success(self, gateway_name: str) -> None:
        """Record successful request for a gateway"""
        breaker = self.get_or_create(gateway_name)
        breaker.record_success()
    
    def record_failure(self, gateway_name: str) -> None:
        """Record failed request for a gateway"""
        breaker = self.get_or_create(gateway_name)
        breaker.record_failure()
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers"""
        with self._lock:
            return {name: breaker.get_status() for name, breaker in self._breakers.items()}
    
    def get_available_gateways(self) -> list:
        """Get list of available gateway names"""
        with self._lock:
            return [name for name, breaker in self._breakers.items() if breaker.is_available()]
    
    def get_unavailable_gateways(self) -> list:
        """Get list of unavailable gateway names"""
        with self._lock:
            return [name for name, breaker in self._breakers.items() if not breaker.is_available()]
    
    def reset_all(self) -> None:
        """Reset all circuit breakers"""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
    
    def reset_gateway(self, gateway_name: str) -> bool:
        """Reset a specific gateway's circuit breaker"""
        with self._lock:
            if gateway_name in self._breakers:
                self._breakers[gateway_name].reset()
                return True
            return False


# Global registry instance
_registry = CircuitBreakerRegistry()


def get_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry"""
    return _registry


def is_gateway_available(gateway_name: str) -> bool:
    """Check if a gateway is available (circuit not open)"""
    return _registry.is_available(gateway_name)


def record_gateway_success(gateway_name: str) -> None:
    """Record a successful gateway request"""
    _registry.record_success(gateway_name)


def record_gateway_failure(gateway_name: str) -> None:
    """Record a failed gateway request"""
    _registry.record_failure(gateway_name)


def is_infrastructure_failure(status_msg: str, proxy_ok: bool) -> bool:
    """
    Determine if a status message indicates an infrastructure failure.
    
    Infrastructure failures (should trip circuit breaker):
    - Network timeouts
    - Connection errors
    - Proxy failures
    - Rate limiting
    - Gateway/API errors (not card declines)
    
    NOT infrastructure failures (should NOT trip circuit breaker):
    - Card declines (including those with "error" in the decline message)
    - CVV mismatches
    - Expired cards
    - Insufficient funds
    - 3DS required
    - Any card-related response from the gateway
    """
    if not status_msg:
        return not proxy_ok
    
    status_lower = status_msg.lower()
    
    # If proxy is marked as dead, it's likely a network issue
    if not proxy_ok:
        return True
    
    # Explicit infrastructure failure patterns (high confidence)
    infra_failure_patterns = [
        "timeout",
        "connection error",
        "connection refused", 
        "connection reset",
        "network error",
        "proxy error",
        "proxy failed",
        "ssl error",
        "certificate",
        "dns",
        "socket",
        "circuit open",
        "rate limit",
        "too many requests",
        "503",
        "502",
        "504",
        "service unavailable",
        "gateway timeout",
    ]
    
    for pattern in infra_failure_patterns:
        if pattern in status_lower:
            return True
    
    # Card-related responses are NOT infrastructure failures
    # Even if they contain "error" (like "card_error", "invalid_cvc error")
    card_response_patterns = [
        "declined",
        "decline",
        "approved",
        "charged",
        "live",
        "ccn",
        "cvv",
        "cvc",
        "expired",
        "invalid",
        "insufficient",
        "3d secure",
        "3ds",
        "authentication",
        "fraud",
        "risk",
        "stolen",
        "lost",
        "do not honor",
        "do_not_honor",
        "card_declined",
        "card_error",
        "incorrect_cvc",
        "invalid_cvc",
        "incorrect_number",
        "pm_",  # PaymentMethod ID
        "pi_",  # PaymentIntent ID
        "seti_",  # SetupIntent ID
    ]
    
    for pattern in card_response_patterns:
        if pattern in status_lower:
            return False
    
    # "error" alone is ambiguous - only count as infra failure if proxy is dead
    if "error" in status_lower:
        # Check if it's a specific error type
        if "gateway error" in status_lower and "card" not in status_lower:
            return True
        # Generic error with live proxy is likely a card decline
        return False
    
    return False


def with_circuit_breaker(gateway_name: str):
    """
    Decorator to wrap gateway functions with circuit breaker protection.
    
    Only counts INFRASTRUCTURE failures (timeout, connection, rate limit) as failures.
    Card declines are NOT counted as failures since the gateway is working correctly.
    
    Usage:
        @with_circuit_breaker("stripe_auth")
        def stripe_auth_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Tuple[str, bool]:
            # Check if circuit allows request
            if not is_gateway_available(gateway_name):
                return (f"[CIRCUIT OPEN] {gateway_name} temporarily disabled", False)
            
            try:
                result = func(*args, **kwargs)
                
                # Determine if it was an infrastructure failure
                if isinstance(result, tuple) and len(result) >= 2:
                    status_msg, proxy_ok = result[0], result[1]
                    
                    # Only count infrastructure failures, not card declines
                    if is_infrastructure_failure(status_msg, proxy_ok):
                        record_gateway_failure(gateway_name)
                    else:
                        record_gateway_success(gateway_name)
                    
                    return result
                else:
                    record_gateway_success(gateway_name)
                    return result
                    
            except Exception as e:
                # Exceptions are always infrastructure failures
                record_gateway_failure(gateway_name)
                return (f"Error: {str(e)}", False)
        
        return wrapper
    return decorator


def get_gateway_status_report() -> str:
    """Get a formatted status report of all gateways"""
    status = _registry.get_all_status()
    
    if not status:
        return "No gateway activity recorded yet."
    
    lines = ["Gateway Circuit Breaker Status:", "=" * 50]
    
    for name, info in sorted(status.items()):
        state_emoji = {
            "closed": "✅",
            "open": "🔴",
            "half_open": "🟡"
        }.get(info["state"], "❓")
        
        line = f"{state_emoji} {name}: {info['state'].upper()} | "
        line += f"Success: {info['success_rate']}% | "
        line += f"Requests: {info['total_requests']}"
        
        if info["state"] == "open":
            line += f" | Retry in: {int(info['time_until_retry'])}s"
        
        lines.append(line)
    
    return "\n".join(lines)
