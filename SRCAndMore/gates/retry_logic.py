"""
Retry Logic Module - Smart retry with exponential backoff for soft failures
Handles throttling, rate limits, and transient errors gracefully
"""

import time
import random
import asyncio
from typing import Callable, Tuple, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
from functools import wraps


class FailureType(Enum):
    """Types of failures that determine retry behavior"""
    HARD = "hard"
    SOFT = "soft"
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    THROTTLED = "throttled"


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: float = 0.3
    retry_on_soft: bool = True
    retry_on_transient: bool = True
    retry_on_rate_limit: bool = True


SOFT_FAILURE_PATTERNS = [
    "try again", "retry", "temporary", "throttled", "rate limit",
    "too many requests", "429", "503", "502", "504", "timeout",
    "connection reset", "connection refused", "ssl error",
    "please wait", "slow down", "overloaded", "busy",
]

HARD_FAILURE_PATTERNS = [
    "declined", "insufficient", "expired", "invalid card",
    "do not honor", "lost card", "stolen card", "fraud",
    "pickup card", "restricted", "not permitted", "cvv",
    "incorrect_cvc", "card_declined", "expired_card",
]

RATE_LIMIT_PATTERNS = [
    "rate limit", "too many", "429", "quota exceeded",
    "requests exceeded", "slow down", "throttl",
]


def classify_failure(error_message: str) -> FailureType:
    """
    Classify failure type based on error message.
    
    Returns:
        FailureType indicating retry strategy
    """
    error_lower = error_message.lower()
    
    for pattern in RATE_LIMIT_PATTERNS:
        if pattern in error_lower:
            return FailureType.RATE_LIMITED
    
    if "throttl" in error_lower:
        return FailureType.THROTTLED
    
    for pattern in HARD_FAILURE_PATTERNS:
        if pattern in error_lower:
            return FailureType.HARD
    
    for pattern in SOFT_FAILURE_PATTERNS:
        if pattern in error_lower:
            return FailureType.SOFT
    
    if "timeout" in error_lower or "connection" in error_lower:
        return FailureType.TRANSIENT
    
    return FailureType.HARD


def should_retry(error_message: str, config: RetryConfig = None) -> bool:
    """
    Determine if a request should be retried based on error.
    
    Args:
        error_message: Error message from failed request
        config: Retry configuration
    
    Returns:
        True if retry should be attempted
    """
    if config is None:
        config = RetryConfig()
    
    failure_type = classify_failure(error_message)
    
    if failure_type == FailureType.HARD:
        return False
    elif failure_type == FailureType.SOFT:
        return config.retry_on_soft
    elif failure_type == FailureType.TRANSIENT:
        return config.retry_on_transient
    elif failure_type in [FailureType.RATE_LIMITED, FailureType.THROTTLED]:
        return config.retry_on_rate_limit
    
    return False


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: float = 0.3
) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        exponential_base: Exponential growth factor
        jitter: Random jitter factor (0-1)
    
    Returns:
        Delay in seconds
    """
    delay = base_delay * (exponential_base ** attempt)
    delay = min(delay, max_delay)
    
    jitter_amount = delay * jitter
    delay += random.uniform(-jitter_amount, jitter_amount)
    
    return max(0.1, delay)


def retry_with_backoff(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    config: RetryConfig = None,
    on_retry: Callable = None,
) -> Any:
    """
    Execute function with retry and exponential backoff.
    
    Args:
        func: Function to execute
        args: Positional arguments
        kwargs: Keyword arguments
        config: Retry configuration
        on_retry: Callback called before each retry (attempt, error, delay)
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    if kwargs is None:
        kwargs = {}
    if config is None:
        config = RetryConfig()
    
    last_error = None
    
    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            if attempt >= config.max_retries:
                raise
            
            if not should_retry(error_msg, config):
                raise
            
            delay = calculate_backoff(
                attempt,
                config.base_delay,
                config.max_delay,
                config.exponential_base,
                config.jitter
            )
            
            if on_retry:
                on_retry(attempt, error_msg, delay)
            
            time.sleep(delay)
    
    raise last_error


async def async_retry_with_backoff(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    config: RetryConfig = None,
    on_retry: Callable = None,
) -> Any:
    """
    Async version of retry_with_backoff.
    """
    if kwargs is None:
        kwargs = {}
    if config is None:
        config = RetryConfig()
    
    last_error = None
    
    for attempt in range(config.max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            if attempt >= config.max_retries:
                raise
            
            if not should_retry(error_msg, config):
                raise
            
            delay = calculate_backoff(
                attempt,
                config.base_delay,
                config.max_delay,
                config.exponential_base,
                config.jitter
            )
            
            if on_retry:
                if asyncio.iscoroutinefunction(on_retry):
                    await on_retry(attempt, error_msg, delay)
                else:
                    on_retry(attempt, error_msg, delay)
            
            await asyncio.sleep(delay)
    
    raise last_error


def with_retry(config: RetryConfig = None):
    """
    Decorator to add retry logic to a function.
    
    Usage:
        @with_retry(RetryConfig(max_retries=3))
        def my_function():
            ...
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_with_backoff(func, args, kwargs, config)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await async_retry_with_backoff(func, args, kwargs, config)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


class ResponseConfidence:
    """
    Assigns confidence scores to gateway responses.
    Helps distinguish "definitely dead" from "maybe rate limited".
    """
    
    HIGH_CONFIDENCE_PATTERNS = {
        "approved": 0.95,
        "success": 0.95,
        "charged": 0.95,
        "do_not_honor": 0.90,
        "insufficient_funds": 0.90,
        "card_declined": 0.85,
        "expired_card": 0.90,
        "incorrect_cvc": 0.85,
        "stolen_card": 0.95,
        "lost_card": 0.95,
        "fraud": 0.85,
    }
    
    LOW_CONFIDENCE_PATTERNS = {
        "try again": 0.30,
        "temporary": 0.35,
        "timeout": 0.25,
        "connection": 0.20,
        "error": 0.40,
        "unknown": 0.30,
        "processing": 0.35,
    }
    
    @classmethod
    def score(cls, response: str) -> Tuple[float, str]:
        """
        Calculate confidence score for a response.
        
        Returns:
            (confidence_score, confidence_label)
        """
        response_lower = response.lower()
        
        for pattern, score in cls.HIGH_CONFIDENCE_PATTERNS.items():
            if pattern in response_lower:
                return (score, "high")
        
        for pattern, score in cls.LOW_CONFIDENCE_PATTERNS.items():
            if pattern in response_lower:
                return (score, "low")
        
        return (0.5, "medium")
    
    @classmethod
    def is_definitive(cls, response: str) -> bool:
        """Check if response is definitely final (no retry needed)"""
        confidence, level = cls.score(response)
        return level == "high" and confidence >= 0.85
    
    @classmethod
    def should_retry_response(cls, response: str) -> bool:
        """Check if response suggests retry might succeed"""
        confidence, level = cls.score(response)
        return level == "low" and confidence < 0.4


def get_response_confidence(response: str) -> Tuple[float, str]:
    """Get confidence score for a gateway response"""
    return ResponseConfidence.score(response)


def is_definitive_response(response: str) -> bool:
    """Check if response is definitive (no retry needed)"""
    return ResponseConfidence.is_definitive(response)


def should_retry_on_response(response: str) -> bool:
    """Check if response suggests retry might help"""
    return ResponseConfidence.should_retry_response(response)
