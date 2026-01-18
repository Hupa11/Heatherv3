"""
Per-gateway metrics collection and reporting.
Tracks elapsed time, success rates, and gateway performance.
"""

import time
import json
import os
from datetime import datetime
from typing import Dict, Optional, Tuple, Callable, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

# Metrics file paths
METRICS_FILE = 'logs/metrics.json'
GATEWAY_STATS_FILE = 'logs/gateway_stats.json'


@dataclass
class GatewayMetrics:
    """Single check metrics"""
    gateway: str
    card: str
    status: str
    elapsed_ms: int
    timestamp: str
    user_id: Optional[int] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


@dataclass
class GatewayStats:
    """Aggregated gateway statistics"""
    gateway: str
    total_checks: int = 0
    approved: int = 0
    declined: int = 0
    errors: int = 0
    avg_elapsed_ms: float = 0.0
    min_elapsed_ms: int = 0
    max_elapsed_ms: int = 0
    approval_rate: float = 0.0
    last_updated: str = ""


class MetricsCollector:
    """Collect and aggregate metrics for all gateways"""
    
    def __init__(self):
        self.gateway_times: Dict[str, list] = defaultdict(list)
        self.gateway_statuses: Dict[str, list] = defaultdict(list)
        os.makedirs('logs', exist_ok=True)
    
    def record_check(self, gateway: str, card: str, status: str, 
                    elapsed_ms: int, user_id: Optional[int] = None,
                    error: Optional[str] = None, raw_response: Optional[str] = None) -> None:
        """Record a single gateway check"""
        metric = GatewayMetrics(
            gateway=gateway,
            card=card,
            status=status,
            elapsed_ms=elapsed_ms,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            error=error,
            raw_response=raw_response
        )
        
        # Append to metrics file
        try:
            with open(METRICS_FILE, 'a') as f:
                f.write(json.dumps(asdict(metric)) + '\n')
        except Exception as e:
            print(f"[!] Error writing metrics: {e}")
        
        # Track in memory
        self.gateway_times[gateway].append(elapsed_ms)
        self.gateway_statuses[gateway].append(status)
    
    def get_gateway_stats(self, gateway: str) -> GatewayStats:
        """Get aggregated stats for a gateway"""
        times = self.gateway_times.get(gateway, [])
        statuses = self.gateway_statuses.get(gateway, [])
        
        total = len(statuses)
        approved = sum(1 for s in statuses if 'APPROVED' in s.upper())
        declined = sum(1 for s in statuses if 'DECLINED' in s.upper())
        errors = sum(1 for s in statuses if 'ERROR' in s.upper() or 'TIMEOUT' in s.upper())
        
        avg_ms = sum(times) / len(times) if times else 0
        min_ms = min(times) if times else 0
        max_ms = max(times) if times else 0
        approval_rate = (approved / total * 100) if total > 0 else 0
        
        return GatewayStats(
            gateway=gateway,
            total_checks=total,
            approved=approved,
            declined=declined,
            errors=errors,
            avg_elapsed_ms=round(avg_ms, 2),
            min_elapsed_ms=min_ms,
            max_elapsed_ms=max_ms,
            approval_rate=round(approval_rate, 2),
            last_updated=datetime.now().isoformat()
        )
    
    def get_all_stats(self) -> Dict[str, GatewayStats]:
        """Get stats for all gateways"""
        stats = {}
        for gateway in self.gateway_times.keys():
            stats[gateway] = self.get_gateway_stats(gateway)
        return stats
    
    def save_stats(self) -> None:
        """Save aggregated stats to file"""
        stats = self.get_all_stats()
        try:
            with open(GATEWAY_STATS_FILE, 'w') as f:
                json.dump(
                    {gw: asdict(s) for gw, s in stats.items()},
                    f,
                    indent=2
                )
        except Exception as e:
            print(f"[!] Error saving gateway stats: {e}")
    
    def print_summary(self) -> str:
        """Print formatted summary of gateway performance"""
        stats = self.get_all_stats()
        if not stats:
            return "No metrics collected yet"
        
        lines = [
            "\n╔════════════════════════════════════════════════════════════════╗",
            "║              GATEWAY PERFORMANCE SUMMARY                      ║",
            "╚════════════════════════════════════════════════════════════════╝\n",
            "Gateway              | Checks | Approved | Declined | Time (ms)  | Rate",
            "─────────────────────┼────────┼──────────┼──────────┼────────────┼──────",
        ]
        
        for gateway in sorted(stats.keys()):
            s = stats[gateway]
            line = (
                f"{gateway:20} | {s.total_checks:6} | "
                f"{s.approved:8} | {s.declined:8} | "
                f"{s.avg_elapsed_ms:10.1f} | {s.approval_rate:5.1f}%"
            )
            lines.append(line)
        
        lines.extend([
            "─────────────────────┴────────┴──────────┴──────────┴────────────┴──────\n"
        ])
        
        return "\n".join(lines)


# Global metrics instance
_metrics = MetricsCollector()


def time_gateway_check(gateway_name: str) -> Callable:
    """Decorator to time gateway function calls"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Tuple[Any, bool]:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = int((time.time() - start_time) * 1000)
                return result, elapsed_ms
            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                raise
        return wrapper
    return decorator


def record_metric(gateway: str, card: str, status: str, elapsed_ms: int,
                 user_id: Optional[int] = None, error: Optional[str] = None) -> None:
    """Record a gateway check metric"""
    _metrics.record_check(gateway, card, status, elapsed_ms, user_id, error)


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector"""
    return _metrics


def get_summary() -> str:
    """Get formatted metrics summary"""
    return _metrics.print_summary()


if __name__ == '__main__':
    # Test metrics collector
    print("Testing Metrics Collector")
    print("=" * 50)
    
    # Simulate some gateway checks
    test_checks = [
        ('stripe', '4111111111111111', 'APPROVED', 1250),
        ('stripe', '4111111111111112', 'DECLINED', 1180),
        ('stripe', '4111111111111113', 'APPROVED', 1290),
        ('paypal', '4111111111111111', 'APPROVED', 2100),
        ('paypal', '4111111111111112', 'APPROVED', 2050),
        ('charge1', '4111111111111111', 'DECLINED', 890),
        ('charge1', '4111111111111112', 'APPROVED', 920),
        ('charge1', '4111111111111113', 'APPROVED', 910),
    ]
    
    collector = MetricsCollector()
    for gateway, card, status, elapsed_ms in test_checks:
        collector.record_check(gateway, card, status, elapsed_ms)
    
    print(collector.print_summary())
    collector.save_stats()
    print("✅ Metrics recorded and saved to logs/metrics.json")
