#!/usr/bin/env python3
"""
Retry Logic with Exponential Backoff for Phase 9

Implements exponential backoff with jitter for resilience:
- Base delay: 1 second
- Max delay: 30 seconds
- Max retries: 3 (configurable)
- Jitter: ±20% randomization

Usage:
    from gates.retry import retry_with_backoff, RetryConfig
    
    # Simple retry with defaults
    result = retry_with_backoff(
        func=gateway_check,
        args=(card, mm, yy, cvc),
    )
    
    # Custom retry configuration
    config = RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=60,
        jitter=0.1
    )
    result = retry_with_backoff(
        func=gateway_check,
        args=(card, mm, yy, cvc),
        config=config
    )
"""

import time
import random
import logging
from typing import Callable, Any, Optional, Tuple, List
from dataclasses import dataclass
from functools import wraps

# Setup logging
logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry logic"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    jitter: float = 0.2  # ±20% randomization
    exponential_base: float = 2.0  # 2^attempt for backoff
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt with exponential backoff and jitter"""
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        raw_delay = self.base_delay * (self.exponential_base ** attempt)
        
        # Cap at max delay
        capped_delay = min(raw_delay, self.max_delay)
        
        # Add jitter (±jitter%)
        jitter_amount = capped_delay * self.jitter
        jitter_offset = random.uniform(-jitter_amount, jitter_amount)
        
        final_delay = max(0, capped_delay + jitter_offset)
        return final_delay


class RetryStats:
    """Track retry statistics"""
    
    def __init__(self):
        self.total_attempts = 0
        self.successful_first_try = 0
        self.successful_after_retries = 0
        self.total_failures = 0
        self.retry_count_distribution = {}
    
    def record_success(self, retries_used: int) -> None:
        """Record a successful call"""
        self.total_attempts += 1
        
        if retries_used == 0:
            self.successful_first_try += 1
        else:
            self.successful_after_retries += 1
        
        self.retry_count_distribution[retries_used] = \
            self.retry_count_distribution.get(retries_used, 0) + 1
    
    def record_failure(self) -> None:
        """Record a failed call (all retries exhausted)"""
        self.total_attempts += 1
        self.total_failures += 1
    
    def get_stats(self) -> dict:
        """Get statistics"""
        success_rate = (self.total_attempts - self.total_failures) / self.total_attempts \
            if self.total_attempts > 0 else 0
        
        avg_retries_needed = 0
        if self.successful_after_retries > 0:
            total_retries_used = sum(
                k * v for k, v in self.retry_count_distribution.items() if k > 0
            )
            avg_retries_needed = total_retries_used / self.successful_after_retries
        
        return {
            'total_attempts': self.total_attempts,
            'successful_first_try': self.successful_first_try,
            'successful_after_retries': self.successful_after_retries,
            'total_failures': self.total_failures,
            'success_rate': success_rate,
            'avg_retries_needed': avg_retries_needed,
            'distribution': self.retry_count_distribution,
        }
    
    def print_stats(self) -> None:
        """Print formatted statistics"""
        stats = self.get_stats()
        
        print("\n" + "="*80)
        print("RETRY STATISTICS")
        print("="*80)
        print(f"Total Attempts:           {stats['total_attempts']}")
        print(f"Successful (1st try):     {stats['successful_first_try']}")
        print(f"Successful (after retry): {stats['successful_after_retries']}")
        print(f"Failed (all retries):     {stats['total_failures']}")
        print(f"Success Rate:             {stats['success_rate']:.1%}")
        print(f"Avg Retries Needed:       {stats['avg_retries_needed']:.2f}")
        print("\nRetry Distribution:")
        for retries in sorted(stats['distribution'].keys()):
            count = stats['distribution'][retries]
            print(f"  {retries} retries: {count} cases")
        print("="*80)


# Global retry stats
_retry_stats = RetryStats()


def retry_with_backoff(
    func: Callable,
    args: Tuple = (),
    kwargs: dict = None,
    config: Optional[RetryConfig] = None,
    allowed_exceptions: Tuple = (Exception,),
    on_retry: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
) -> Any:
    """
    Execute function with retry logic and exponential backoff
    
    Args:
        func: Function to call
        args: Positional arguments
        kwargs: Keyword arguments
        config: RetryConfig (uses defaults if None)
        allowed_exceptions: Exceptions that trigger retry (others re-raise)
        on_retry: Callback called before each retry (called with attempt #)
        on_failure: Callback called when all retries exhausted
    
    Returns:
        Function result if successful
    
    Raises:
        Exception: Original exception if all retries exhausted
    """
    if kwargs is None:
        kwargs = {}
    
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_retries + 1):
        try:
            result = func(*args, **kwargs)
            _retry_stats.record_success(attempt)
            
            if attempt > 0:
                logger.info(f"✅ {func.__name__} succeeded after {attempt} retries")
            
            return result
        
        except Exception as e:
            last_exception = e
            
            # Check if this exception type should trigger retry
            if not isinstance(e, allowed_exceptions):
                raise
            
            # Check if we have retries left
            if attempt >= config.max_retries:
                logger.error(f"❌ {func.__name__} failed after {config.max_retries} retries")
                _retry_stats.record_failure()
                
                if on_failure:
                    on_failure(attempt, e)
                
                raise
            
            # Calculate delay
            delay = config.get_delay(attempt)
            
            logger.warning(
                f"⚠️  {func.__name__} failed (attempt {attempt+1}/{config.max_retries+1}): {str(e)[:100]}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            if on_retry:
                on_retry(attempt, delay, e)
            
            # Wait before retry
            time.sleep(delay)
    
    # Should never reach here, but just in case
    _retry_stats.record_failure()
    raise last_exception


def retry_decorator(
    max_retries: int = 3,
    base_delay: float = 1.0,
    allowed_exceptions: Tuple = (Exception,),
):
    """
    Decorator for automatic retry with backoff
    
    Usage:
        @retry_decorator(max_retries=5, base_delay=0.5)
        def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
            return retry_with_backoff(
                func=func,
                args=args,
                kwargs=kwargs,
                config=config,
                allowed_exceptions=allowed_exceptions,
            )
        return wrapper
    return decorator


def get_retry_stats() -> dict:
    """Get global retry statistics"""
    return _retry_stats.get_stats()


def print_retry_stats() -> None:
    """Print global retry statistics"""
    _retry_stats.print_stats()


def reset_retry_stats() -> None:
    """Reset retry statistics"""
    global _retry_stats
    _retry_stats = RetryStats()


# Common retry configurations
FAST_RETRY = RetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=10,
)

STANDARD_RETRY = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30,
)

AGGRESSIVE_RETRY = RetryConfig(
    max_retries=5,
    base_delay=0.5,
    max_delay=60,
)

PATIENT_RETRY = RetryConfig(
    max_retries=10,
    base_delay=2.0,
    max_delay=120,
)


if __name__ == '__main__':
    # Test retry logic
    print("Testing Retry Logic with Exponential Backoff...")
    print()
    
    # Test 1: Function that fails then succeeds
    attempt_count = 0
    
    def flaky_function():
        global attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ValueError(f"Attempt {attempt_count} failed")
        return "Success!"
    
    attempt_count = 0
    result = retry_with_backoff(flaky_function)
    print(f"Test 1 - Flaky function result: {result}\n")
    
    # Test 2: Decorator usage
    @retry_decorator(max_retries=3, base_delay=0.5)
    def another_flaky_function():
        if random.random() < 0.7:
            raise ConnectionError("Network error")
        return "Connected!"
    
    result = another_flaky_function()
    print(f"Test 2 - Decorated function result: {result}\n")
    
    # Print stats
    print_retry_stats()
