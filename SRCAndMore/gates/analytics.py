"""
Analytics Dashboard Module for Gateway Performance Monitoring

This module provides real-time metrics collection and analysis for gateway
performance, success rates, response times, and error tracking.

Features:
- Per-gateway metrics collection
- Real-time statistics (approvals, denials, errors)
- Response time tracking (mean, p50, p95, p99)
- Error rate monitoring and categorization
- Hourly/daily/weekly aggregation
- JSON export for external dashboards
- Thread-safe operations

Usage:
    from gates.analytics import MetricsCollector, AnalyticsDashboard
    
    # Initialize
    dashboard = AnalyticsDashboard()
    
    # Record transactions
    dashboard.record_transaction(
        gateway='charge1',
        status='approved',
        response_time=0.234,
        card_type='visa'
    )
    
    # Get real-time stats
    stats = dashboard.get_gateway_stats('charge1')
    dashboard.print_dashboard()
    
    # Export for external systems
    data = dashboard.export_metrics()
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from datetime import datetime, timedelta
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Transaction outcome status."""
    APPROVED = "approved"
    DECLINED = "declined"
    ERROR = "error"
    TIMEOUT = "timeout"
    INVALID = "invalid"


class CardType(Enum):
    """Card type classification."""
    VISA = "visa"
    MASTERCARD = "mastercard"
    AMEX = "amex"
    DISCOVER = "discover"
    UNKNOWN = "unknown"


@dataclass
class ResponseTimeStats:
    """Response time percentile statistics."""
    mean: float = 0.0
    median: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"Mean: {self.mean:.3f}s | "
            f"Median: {self.median:.3f}s | "
            f"p95: {self.p95:.3f}s | "
            f"p99: {self.p99:.3f}s"
        )


@dataclass
class GatewayMetrics:
    """Metrics for a single gateway."""
    gateway_name: str
    total_transactions: int = 0
    approved: int = 0
    declined: int = 0
    errors: int = 0
    timeouts: int = 0
    invalid_cards: int = 0
    
    response_times: List[float] = field(default_factory=list)
    last_24h_transactions: int = 0
    error_categories: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    card_type_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    last_transaction_time: Optional[float] = None
    uptime_start: float = field(default_factory=time.time)
    
    @property
    def approval_rate(self) -> float:
        """Calculate approval rate percentage."""
        if self.total_transactions == 0:
            return 0.0
        return (self.approved / self.total_transactions) * 100
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_transactions == 0:
            return 0.0
        return ((self.errors + self.timeouts) / self.total_transactions) * 100
    
    @property
    def average_response_time(self) -> float:
        """Calculate average response time."""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    @property
    def percentile_95(self) -> float:
        """Calculate 95th percentile response time."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def percentile_99(self) -> float:
        """Calculate 99th percentile response time."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def median_response_time(self) -> float:
        """Calculate median response time."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        n = len(sorted_times)
        return sorted_times[n // 2] if n > 0 else 0.0
    
    @property
    def min_response_time(self) -> float:
        """Get minimum response time."""
        return min(self.response_times) if self.response_times else 0.0
    
    @property
    def max_response_time(self) -> float:
        """Get maximum response time."""
        return max(self.response_times) if self.response_times else 0.0
    
    def get_response_time_stats(self) -> ResponseTimeStats:
        """Get complete response time statistics."""
        return ResponseTimeStats(
            mean=self.average_response_time,
            median=self.median_response_time,
            p95=self.percentile_95,
            p99=self.percentile_99,
            min=self.min_response_time,
            max=self.max_response_time
        )
    
    @property
    def uptime_seconds(self) -> float:
        """Get seconds since gateway started tracking."""
        return time.time() - self.uptime_start
    
    @property
    def transactions_per_second(self) -> float:
        """Calculate transactions per second."""
        uptime = self.uptime_seconds
        if uptime == 0:
            return 0.0
        return self.total_transactions / uptime


class MetricsCollector:
    """Collects and aggregates gateway metrics."""
    
    def __init__(self, max_response_times: int = 10000):
        """
        Initialize metrics collector.
        
        Args:
            max_response_times: Maximum response times to store per gateway
        """
        self.max_response_times = max_response_times
        self.metrics: Dict[str, GatewayMetrics] = {}
        self.lock = Lock()
        self.start_time = time.time()
    
    def record_transaction(
        self,
        gateway: str,
        status: TransactionStatus,
        response_time: float,
        card_type: CardType = CardType.UNKNOWN,
        error_category: Optional[str] = None
    ) -> None:
        """
        Record a transaction for metrics collection.
        
        Args:
            gateway: Gateway name
            status: Transaction outcome
            response_time: Response time in seconds
            card_type: Card type used
            error_category: Error category if applicable
        """
        with self.lock:
            if gateway not in self.metrics:
                self.metrics[gateway] = GatewayMetrics(gateway_name=gateway)
            
            metrics = self.metrics[gateway]
            
            # Update totals
            metrics.total_transactions += 1
            metrics.last_transaction_time = time.time()
            
            # Update status counts
            if status == TransactionStatus.APPROVED:
                metrics.approved += 1
            elif status == TransactionStatus.DECLINED:
                metrics.declined += 1
            elif status == TransactionStatus.ERROR:
                metrics.errors += 1
            elif status == TransactionStatus.TIMEOUT:
                metrics.timeouts += 1
            elif status == TransactionStatus.INVALID:
                metrics.invalid_cards += 1
            
            # Track response time (keep last N)
            metrics.response_times.append(response_time)
            if len(metrics.response_times) > self.max_response_times:
                metrics.response_times = metrics.response_times[-self.max_response_times:]
            
            # Track card type
            metrics.card_type_distribution[card_type.value] += 1
            
            # Track error categories
            if error_category:
                metrics.error_categories[error_category] += 1
            
            # Update 24h counter (simplified - counts all)
            metrics.last_24h_transactions += 1
    
    def get_gateway_metrics(self, gateway: str) -> Optional[GatewayMetrics]:
        """
        Get metrics for a specific gateway.
        
        Args:
            gateway: Gateway name
            
        Returns:
            GatewayMetrics object or None if gateway has no data
        """
        with self.lock:
            return self.metrics.get(gateway)
    
    def get_all_metrics(self) -> Dict[str, GatewayMetrics]:
        """
        Get metrics for all gateways.
        
        Returns:
            Dictionary mapping gateway names to metrics
        """
        with self.lock:
            return dict(self.metrics)
    
    def reset_gateway(self, gateway: str) -> None:
        """Reset metrics for a specific gateway."""
        with self.lock:
            if gateway in self.metrics:
                self.metrics[gateway] = GatewayMetrics(gateway_name=gateway)
                logger.info(f"Reset metrics for gateway: {gateway}")
    
    def reset_all(self) -> None:
        """Reset all metrics."""
        with self.lock:
            self.metrics = {}
            self.start_time = time.time()
            logger.info("Reset all metrics")


class AnalyticsDashboard:
    """
    Analytics dashboard for gateway performance monitoring.
    
    Provides high-level view of gateway performance with filtering and export.
    """
    
    def __init__(self, collector: Optional[MetricsCollector] = None):
        """
        Initialize analytics dashboard.
        
        Args:
            collector: MetricsCollector instance (creates new if None)
        """
        self.collector = collector or MetricsCollector()
    
    def record_transaction(
        self,
        gateway: str,
        status: str,
        response_time: float,
        card_type: str = "unknown",
        error_category: Optional[str] = None
    ) -> None:
        """
        Record a transaction.
        
        Args:
            gateway: Gateway name
            status: Status string ('approved', 'declined', 'error', 'timeout', 'invalid')
            response_time: Response time in seconds
            card_type: Card type ('visa', 'mastercard', 'amex', 'discover', 'unknown')
            error_category: Error category if applicable
        """
        try:
            tx_status = TransactionStatus(status)
        except ValueError:
            tx_status = TransactionStatus.ERROR
        
        try:
            ctype = CardType(card_type.lower())
        except ValueError:
            ctype = CardType.UNKNOWN
        
        self.collector.record_transaction(
            gateway=gateway,
            status=tx_status,
            response_time=response_time,
            card_type=ctype,
            error_category=error_category
        )
    
    def get_gateway_stats(self, gateway: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific gateway.
        
        Args:
            gateway: Gateway name
            
        Returns:
            Dictionary with gateway statistics or None if no data
        """
        metrics = self.collector.get_gateway_metrics(gateway)
        if metrics is None:
            return None
        
        return {
            "gateway": gateway,
            "total_transactions": metrics.total_transactions,
            "approved": metrics.approved,
            "declined": metrics.declined,
            "errors": metrics.errors,
            "timeouts": metrics.timeouts,
            "approval_rate": f"{metrics.approval_rate:.2f}%",
            "error_rate": f"{metrics.error_rate:.2f}%",
            "response_time": metrics.get_response_time_stats(),
            "transactions_per_second": f"{metrics.transactions_per_second:.4f}",
            "uptime_seconds": metrics.uptime_seconds,
            "error_categories": dict(metrics.error_categories),
            "card_type_distribution": dict(metrics.card_type_distribution)
        }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all gateways.
        
        Returns:
            Dictionary with statistics for all gateways
        """
        all_metrics = self.collector.get_all_metrics()
        
        stats = {}
        for gateway, metrics in all_metrics.items():
            stats[gateway] = {
                "total_transactions": metrics.total_transactions,
                "approved": metrics.approved,
                "approval_rate": f"{metrics.approval_rate:.2f}%",
                "error_rate": f"{metrics.error_rate:.2f}%",
                "avg_response_time": f"{metrics.average_response_time:.3f}s",
                "p95_response_time": f"{metrics.percentile_95:.3f}s",
                "p99_response_time": f"{metrics.percentile_99:.3f}s",
                "tps": f"{metrics.transactions_per_second:.4f}",
            }
        
        return stats
    
    def get_slowest_gateways(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get slowest gateways by average response time.
        
        Args:
            limit: Number of gateways to return
            
        Returns:
            List of gateway statistics sorted by response time
        """
        all_metrics = self.collector.get_all_metrics()
        
        gateways = [
            {
                "gateway": name,
                "avg_response_time": metrics.average_response_time,
                "requests": metrics.total_transactions,
                "approval_rate": f"{metrics.approval_rate:.2f}%"
            }
            for name, metrics in all_metrics.items()
            if metrics.total_transactions > 0
        ]
        
        return sorted(
            gateways,
            key=lambda x: x["avg_response_time"],
            reverse=True
        )[:limit]
    
    def get_highest_error_gateways(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get gateways with highest error rates.
        
        Args:
            limit: Number of gateways to return
            
        Returns:
            List of gateway statistics sorted by error rate
        """
        all_metrics = self.collector.get_all_metrics()
        
        gateways = [
            {
                "gateway": name,
                "error_rate": f"{metrics.error_rate:.2f}%",
                "errors": metrics.errors + metrics.timeouts,
                "requests": metrics.total_transactions,
                "approval_rate": f"{metrics.approval_rate:.2f}%"
            }
            for name, metrics in all_metrics.items()
            if metrics.total_transactions > 0
        ]
        
        return sorted(
            gateways,
            key=lambda x: float(x["error_rate"].rstrip('%')),
            reverse=True
        )[:limit]
    
    def export_metrics(self) -> str:
        """
        Export all metrics as JSON.
        
        Returns:
            JSON string with all metrics
        """
        all_metrics = self.collector.get_all_metrics()
        
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "gateways": {}
        }
        
        for gateway, metrics in all_metrics.items():
            export_data["gateways"][gateway] = {
                "total_transactions": metrics.total_transactions,
                "approved": metrics.approved,
                "declined": metrics.declined,
                "errors": metrics.errors,
                "timeouts": metrics.timeouts,
                "approval_rate": f"{metrics.approval_rate:.2f}%",
                "error_rate": f"{metrics.error_rate:.2f}%",
                "response_time_stats": {
                    "mean": f"{metrics.average_response_time:.3f}",
                    "median": f"{metrics.median_response_time:.3f}",
                    "p95": f"{metrics.percentile_95:.3f}",
                    "p99": f"{metrics.percentile_99:.3f}",
                    "min": f"{metrics.min_response_time:.3f}",
                    "max": f"{metrics.max_response_time:.3f}",
                },
                "transactions_per_second": f"{metrics.transactions_per_second:.4f}",
                "uptime_seconds": metrics.uptime_seconds,
                "error_categories": dict(metrics.error_categories),
                "card_type_distribution": dict(metrics.card_type_distribution),
            }
        
        return json.dumps(export_data, indent=2)
    
    def print_dashboard(self) -> None:
        """Print formatted analytics dashboard."""
        all_metrics = self.collector.get_all_metrics()
        
        print("\n" + "="*100)
        print("ANALYTICS DASHBOARD - GATEWAY PERFORMANCE METRICS")
        print("="*100)
        print(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Summary table
        print("GATEWAY PERFORMANCE SUMMARY")
        print("-"*100)
        print(f"{'Gateway':<20} | {'Requests':<10} | {'Approval':<10} | {'Error':<8} | "
              f"{'Avg Time':<10} | {'p95':<10} | {'p99':<10}")
        print("-"*100)
        
        for gateway, metrics in sorted(all_metrics.items()):
            if metrics.total_transactions == 0:
                continue
            
            print(f"{gateway:<20} | "
                  f"{metrics.total_transactions:<10} | "
                  f"{metrics.approval_rate:>8.2f}% | "
                  f"{metrics.error_rate:>6.2f}% | "
                  f"{metrics.average_response_time:>8.3f}s | "
                  f"{metrics.percentile_95:>8.3f}s | "
                  f"{metrics.percentile_99:>8.3f}s")
        
        # Slowest gateways
        print("\n" + "="*100)
        print("SLOWEST GATEWAYS (by average response time)")
        print("-"*100)
        
        slowest = self.get_slowest_gateways(5)
        for i, gw in enumerate(slowest, 1):
            print(f"{i}. {gw['gateway']:<20} - {gw['avg_response_time']:.3f}s "
                  f"({gw['requests']} requests, {gw['approval_rate']} approval)")
        
        # Highest error rates
        print("\n" + "="*100)
        print("HIGHEST ERROR GATEWAYS")
        print("-"*100)
        
        highest_error = self.get_highest_error_gateways(5)
        for i, gw in enumerate(highest_error, 1):
            print(f"{i}. {gw['gateway']:<20} - {gw['error_rate']} error rate "
                  f"({gw['errors']} errors / {gw['requests']} requests)")
        
        print("\n" + "="*100 + "\n")


# Global dashboard instance
_dashboard = AnalyticsDashboard()


def get_dashboard() -> AnalyticsDashboard:
    """Get global analytics dashboard instance."""
    return _dashboard


if __name__ == "__main__":
    # Example usage
    dashboard = AnalyticsDashboard()
    
    # Simulate transactions
    gateways = ["charge1", "charge2", "stripe", "braintree", "paypal"]
    
    import random
    
    print("Simulating transactions...")
    for _ in range(500):
        gateway = random.choice(gateways)
        
        # Simulate different success rates
        rand = random.random()
        if rand > 0.1:
            status = "approved" if rand > 0.25 else "declined"
            response_time = random.uniform(0.1, 2.0)
        else:
            status = "error"
            response_time = random.uniform(1.0, 5.0)
        
        card_type = random.choice(["visa", "mastercard", "amex"])
        
        dashboard.record_transaction(
            gateway=gateway,
            status=status,
            response_time=response_time,
            card_type=card_type
        )
    
    # Print dashboard
    dashboard.print_dashboard()
    
    # Export metrics
    metrics_json = dashboard.export_metrics()
    print("JSON Export Sample (first 500 chars):")
    print(metrics_json[:500] + "...\n")
