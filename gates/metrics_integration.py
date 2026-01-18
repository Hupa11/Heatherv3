"""
Metrics Integration Module for Gateway Instrumentation

This module provides easy integration points for metrics collection
across all gateways. Wraps the analytics dashboard with convenient
functions for transaction recording.

Usage:
    from gates.metrics_integration import record_gateway_transaction, get_analytics
    
    # Record a transaction
    record_gateway_transaction(
        gateway='charge1',
        card_num='4111111111111111',
        approved=True,
        response_time=0.234,
        error_msg=None
    )
    
    # Get analytics
    dashboard = get_analytics()
    dashboard.print_dashboard()
    
    # Export for external systems
    export = dashboard.export_metrics()
"""

import time
import logging
from typing import Optional
from gates.analytics import AnalyticsDashboard, TransactionStatus, CardType

logger = logging.getLogger(__name__)

# Global analytics instance
_analytics = AnalyticsDashboard()


def get_analytics() -> AnalyticsDashboard:
    """Get global analytics dashboard instance."""
    return _analytics


def _detect_card_type(card_number: str) -> str:
    """
    Detect card type from card number.
    
    Args:
        card_number: Card number string
        
    Returns:
        Card type string
    """
    if not card_number:
        return "unknown"
    
    # Remove spaces and dashes
    card = card_number.replace(" ", "").replace("-", "")
    
    if len(card) < 4:
        return "unknown"
    
    # Check first digit(s) for card type
    if card.startswith("4"):
        return "visa"
    elif card.startswith(("51", "52", "53", "54", "55")):
        return "mastercard"
    elif card.startswith(("34", "37")):
        return "amex"
    elif card.startswith(("6011", "622126", "644", "645", "646", "647", "648")):
        return "discover"
    else:
        return "unknown"


def record_gateway_transaction(
    gateway: str,
    card_num: Optional[str] = None,
    approved: bool = False,
    response_time: float = 0.0,
    error_msg: Optional[str] = None,
    mm: Optional[str] = None,
    yy: Optional[str] = None,
    cvc: Optional[str] = None
) -> None:
    """
    Record a gateway transaction with automatic analysis.
    
    This is the primary integration point for recording transactions
    from any gateway.
    
    Args:
        gateway: Gateway name (e.g., 'charge1', 'stripe')
        card_num: Card number (used for type detection)
        approved: Whether transaction was approved
        response_time: Response time in seconds
        error_msg: Error message if applicable
        mm: Month (for additional tracking)
        yy: Year (for additional tracking)
        cvc: CVC (included for reference)
    """
    # Determine status
    if error_msg:
        status = "error"
        error_category = _categorize_error(error_msg)
    elif not approved:
        status = "declined"
        error_category = None
    else:
        status = "approved"
        error_category = None
    
    # Detect card type
    card_type = _detect_card_type(card_num or "")
    
    # Record to analytics
    _analytics.record_transaction(
        gateway=gateway,
        status=status,
        response_time=response_time,
        card_type=card_type,
        error_category=error_category
    )
    
    # Log transaction
    log_level = logging.WARNING if error_msg else logging.INFO
    logger.log(
        log_level,
        f"Gateway: {gateway} | Status: {status} | "
        f"Time: {response_time:.3f}s | Card: {card_type} | "
        f"Error: {error_msg or 'None'}"
    )


def record_timeout(gateway: str, timeout_seconds: float) -> None:
    """
    Record a timeout event.
    
    Args:
        gateway: Gateway name
        timeout_seconds: Timeout duration
    """
    _analytics.record_transaction(
        gateway=gateway,
        status="timeout",
        response_time=timeout_seconds,
        error_category="timeout"
    )
    logger.warning(f"Gateway {gateway} timed out after {timeout_seconds}s")


def record_invalid_card(gateway: str, card_num: Optional[str] = None) -> None:
    """
    Record an invalid card detection.
    
    Args:
        gateway: Gateway name
        card_num: Card number (optional, for type detection)
    """
    card_type = _detect_card_type(card_num or "")
    
    _analytics.record_transaction(
        gateway=gateway,
        status="invalid",
        response_time=0.0,
        card_type=card_type,
        error_category="invalid_card"
    )
    logger.warning(f"Gateway {gateway} received invalid card ({card_type})")


def _categorize_error(error_msg: str) -> str:
    """
    Categorize error message into error category.
    
    Args:
        error_msg: Error message string
        
    Returns:
        Error category string
    """
    error_lower = error_msg.lower()
    
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"
    elif "connection" in error_lower or "refused" in error_lower:
        return "connection_error"
    elif "invalid" in error_lower or "malformed" in error_lower:
        return "invalid_request"
    elif "rate" in error_lower or "limit" in error_lower:
        return "rate_limit"
    elif "auth" in error_lower or "unauthorized" in error_lower:
        return "authentication_error"
    elif "ssl" in error_lower or "tls" in error_lower or "certificate" in error_lower:
        return "ssl_error"
    elif "dns" in error_lower:
        return "dns_error"
    elif "503" in error_msg or "500" in error_msg:
        return "server_error"
    else:
        return "other_error"


def get_gateway_stats(gateway: str):
    """
    Get statistics for a specific gateway.
    
    Args:
        gateway: Gateway name
        
    Returns:
        Statistics dictionary or None
    """
    return _analytics.get_gateway_stats(gateway)


def get_all_stats():
    """
    Get statistics for all gateways.
    
    Returns:
        Statistics dictionary
    """
    return _analytics.get_all_stats()


def get_slowest_gateways(limit: int = 5):
    """
    Get slowest gateways by response time.
    
    Args:
        limit: Number of gateways to return
        
    Returns:
        List of gateway statistics
    """
    return _analytics.get_slowest_gateways(limit)


def get_highest_error_gateways(limit: int = 5):
    """
    Get gateways with highest error rates.
    
    Args:
        limit: Number of gateways to return
        
    Returns:
        List of gateway statistics
    """
    return _analytics.get_highest_error_gateways(limit)


def print_dashboard() -> None:
    """Print analytics dashboard to console."""
    _analytics.print_dashboard()


def export_metrics() -> str:
    """Export all metrics as JSON string."""
    return _analytics.export_metrics()


def reset_analytics(gateway: Optional[str] = None) -> None:
    """
    Reset analytics data.
    
    Args:
        gateway: Specific gateway to reset (all if None)
    """
    if gateway:
        _analytics.collector.reset_gateway(gateway)
    else:
        _analytics.collector.reset_all()
    logger.info(f"Reset analytics for: {gateway or 'all gateways'}")
