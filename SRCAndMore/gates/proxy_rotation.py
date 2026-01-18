"""
Proxy Rotation Module for Gateway Load Balancing

This module provides intelligent proxy rotation across multiple gateways
with failure tracking, auto-recovery, and health checks.

Features:
- Per-gateway proxy selection
- Failure tracking and automatic blacklisting
- Proxy health monitoring
- Auto-recovery with exponential backoff
- Statistics tracking
- Thread-safe operations

Usage:
    from gates.proxy_rotation import ProxyRotator
    
    rotator = ProxyRotator()
    proxy = rotator.get_next_proxy(gateway='charge1')
    
    # After use, report success or failure
    rotator.mark_proxy_success(proxy, gateway='charge1')
    # OR
    rotator.mark_proxy_failure(proxy, gateway='charge1')
    
    # Get stats
    stats = rotator.get_stats()
    rotator.print_stats()
    
    # Manual health check
    rotator.run_health_check()
"""

import time
import random
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProxyStatus(Enum):
    """Proxy health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    BLACKLISTED = "blacklisted"


@dataclass
class ProxyStats:
    """Statistics for a single proxy."""
    proxy_url: str
    gateway: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_used: Optional[float] = None
    last_failed: Optional[float] = None
    blacklist_time: Optional[float] = None
    status: ProxyStatus = ProxyStatus.HEALTHY
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def is_blacklisted(self) -> bool:
        """Check if proxy is currently blacklisted."""
        if self.blacklist_time is None:
            return False
        # Auto-recovery: blacklist expires after 5 minutes
        if time.time() - self.blacklist_time > 300:
            return False
        return True
    
    @property
    def time_since_failure(self) -> Optional[float]:
        """Get seconds since last failure."""
        if self.last_failed is None:
            return None
        return time.time() - self.last_failed
    
    def __str__(self) -> str:
        """String representation of proxy stats."""
        status_icon = {
            ProxyStatus.HEALTHY: "✅",
            ProxyStatus.DEGRADED: "⚠️",
            ProxyStatus.UNHEALTHY: "❌",
            ProxyStatus.BLACKLISTED: "🚫",
        }
        
        icon = status_icon.get(self.status, "❓")
        success_pct = f"{self.success_rate:.1f}%"
        
        return (
            f"{icon} {self.proxy_url:<25} | "
            f"Success: {success_pct:<6} | "
            f"Requests: {self.total_requests:<4} | "
            f"Failed: {self.consecutive_failures}"
        )


class ProxyRotator:
    """
    Intelligent proxy rotation with health monitoring.
    
    Tracks per-gateway proxy usage, failures, and success rates.
    Automatically blacklists problematic proxies and recovers them.
    """
    
    # Default proxy list (can be overridden via config)
    DEFAULT_PROXIES = [
        "http://proxy1.gateway.local:8080",
        "http://proxy2.gateway.local:8080",
        "http://proxy3.gateway.local:8080",
        "http://proxy4.gateway.local:8080",
        "http://proxy5.gateway.local:8080",
    ]
    
    # Configuration
    FAILURE_THRESHOLD = 3          # Failures before blacklisting
    SUCCESS_THRESHOLD = 5          # Successes to mark as recovered
    BLACKLIST_DURATION = 300       # 5 minutes
    HEALTH_CHECK_INTERVAL = 60     # 1 minute
    DEGRADED_SUCCESS_RATE = 75     # Below this = degraded
    UNHEALTHY_SUCCESS_RATE = 50    # Below this = unhealthy
    
    def __init__(self, proxies: Optional[List[str]] = None):
        """
        Initialize proxy rotator.
        
        Args:
            proxies: List of proxy URLs. Uses DEFAULT_PROXIES if None.
        """
        self.proxies = proxies or self.DEFAULT_PROXIES
        self.stats: Dict[Tuple[str, str], ProxyStats] = {}
        self.lock = Lock()
        self.last_health_check = time.time()
        
        # Initialize stats for all proxies
        for proxy in self.proxies:
            for gateway in self._get_common_gateways():
                key = (proxy, gateway)
                self.stats[key] = ProxyStats(
                    proxy_url=proxy,
                    gateway=gateway
                )
    
    @staticmethod
    def _get_common_gateways() -> List[str]:
        """Get list of common gateway names."""
        return [
            "charge1", "charge2", "charge3", "charge4", "charge5",
            "stripe", "stripe_auth", "braintree", "paypal",
            "shopify", "shopify_nano", "checkout", "aci", "cyberspace",
            "sagepay", "ccavenue", "pagora"
        ]
    
    def get_next_proxy(self, gateway: str = "default") -> str:
        """
        Get next proxy for the given gateway.
        
        Selects from healthy proxies using weighted round-robin.
        Prefers proxies with higher success rates.
        
        Args:
            gateway: Gateway name for proxy selection
            
        Returns:
            Proxy URL string
        """
        with self.lock:
            # Get all proxies for this gateway
            gateway_proxies = [
                (proxy, stats) for (proxy, gw), stats in self.stats.items()
                if gw == gateway and not stats.is_blacklisted
            ]
            
            if not gateway_proxies:
                # All proxies blacklisted, return random one
                logger.warning(f"All proxies for {gateway} blacklisted, selecting random")
                return random.choice(self.proxies)
            
            # Weight by success rate (favor healthier proxies)
            weighted_proxies = []
            for proxy, stats in gateway_proxies:
                weight = max(1, int(stats.success_rate / 20))  # 5-20 weight buckets
                weighted_proxies.extend([proxy] * weight)
            
            return random.choice(weighted_proxies)
    
    def mark_proxy_success(self, proxy: str, gateway: str = "default") -> None:
        """
        Mark proxy usage as successful.
        
        Args:
            proxy: Proxy URL
            gateway: Gateway name
        """
        with self.lock:
            key = (proxy, gateway)
            if key not in self.stats:
                self.stats[key] = ProxyStats(proxy_url=proxy, gateway=gateway)
            
            stats = self.stats[key]
            stats.total_requests += 1
            stats.successful_requests += 1
            stats.last_used = time.time()
            stats.consecutive_failures = 0
            
            # Remove from blacklist if recovered
            if stats.is_blacklisted:
                stats.blacklist_time = None
                logger.info(f"Proxy {proxy} recovered for {gateway}")
            
            # Update status based on success rate
            self._update_proxy_status(stats)
    
    def mark_proxy_failure(self, proxy: str, gateway: str = "default") -> None:
        """
        Mark proxy usage as failed.
        
        Args:
            proxy: Proxy URL
            gateway: Gateway name
        """
        with self.lock:
            key = (proxy, gateway)
            if key not in self.stats:
                self.stats[key] = ProxyStats(proxy_url=proxy, gateway=gateway)
            
            stats = self.stats[key]
            stats.total_requests += 1
            stats.failed_requests += 1
            stats.consecutive_failures += 1
            stats.last_failed = time.time()
            stats.last_used = time.time()
            
            # Blacklist if threshold exceeded
            if stats.consecutive_failures >= self.FAILURE_THRESHOLD:
                stats.blacklist_time = time.time()
                stats.status = ProxyStatus.BLACKLISTED
                logger.warning(
                    f"Proxy {proxy} blacklisted for {gateway} "
                    f"({stats.consecutive_failures} failures)"
                )
            else:
                self._update_proxy_status(stats)
    
    def _update_proxy_status(self, stats: ProxyStats) -> None:
        """Update proxy status based on success rate."""
        if stats.is_blacklisted:
            stats.status = ProxyStatus.BLACKLISTED
        elif stats.success_rate >= 90:
            stats.status = ProxyStatus.HEALTHY
        elif stats.success_rate >= self.DEGRADED_SUCCESS_RATE:
            stats.status = ProxyStatus.DEGRADED
        elif stats.success_rate >= self.UNHEALTHY_SUCCESS_RATE:
            stats.status = ProxyStatus.UNHEALTHY
        else:
            stats.status = ProxyStatus.UNHEALTHY
    
    def run_health_check(self) -> Dict[str, any]:
        """
        Run health check on all proxies.
        
        Returns:
            Dictionary with health check results
        """
        with self.lock:
            now = time.time()
            self.last_health_check = now
            
            results = {
                "timestamp": now,
                "total_proxies": len(self.proxies),
                "healthy_proxies": 0,
                "degraded_proxies": 0,
                "unhealthy_proxies": 0,
                "blacklisted_proxies": 0,
                "recovered_proxies": 0,
                "details": {}
            }
            
            for proxy in self.proxies:
                proxy_stats = [
                    (gw, stats) for (p, gw), stats in self.stats.items()
                    if p == proxy
                ]
                
                if not proxy_stats:
                    continue
                
                # Average stats across gateways for this proxy
                avg_success_rate = sum(
                    stats.success_rate for _, stats in proxy_stats
                ) / len(proxy_stats)
                
                # Check for recovery candidates (was blacklisted, now healthy)
                was_blacklisted = any(
                    stats.blacklist_time and 
                    now - stats.blacklist_time > self.BLACKLIST_DURATION
                    for _, stats in proxy_stats
                )
                
                if was_blacklisted:
                    results["recovered_proxies"] += 1
                    # Reset blacklist times
                    for _, stats in proxy_stats:
                        if stats.is_blacklisted and now - stats.blacklist_time > self.BLACKLIST_DURATION:
                            stats.blacklist_time = None
                            stats.consecutive_failures = 0
                            logger.info(f"Proxy {proxy} auto-recovered")
                
                # Count statuses
                for _, stats in proxy_stats:
                    if stats.status == ProxyStatus.HEALTHY:
                        results["healthy_proxies"] += 1
                    elif stats.status == ProxyStatus.DEGRADED:
                        results["degraded_proxies"] += 1
                    elif stats.status == ProxyStatus.UNHEALTHY:
                        results["unhealthy_proxies"] += 1
                    elif stats.status == ProxyStatus.BLACKLISTED:
                        results["blacklisted_proxies"] += 1
                
                results["details"][proxy] = {
                    "success_rate": f"{avg_success_rate:.1f}%",
                    "total_requests": sum(stats.total_requests for _, stats in proxy_stats),
                    "gateway_stats": [
                        {
                            "gateway": gw,
                            "success_rate": f"{stats.success_rate:.1f}%",
                            "requests": stats.total_requests,
                            "failures": stats.failed_requests,
                            "status": stats.status.value
                        }
                        for gw, stats in proxy_stats
                    ]
                }
            
            logger.info(f"Health check complete: {results['healthy_proxies']} healthy, "
                       f"{results['degraded_proxies']} degraded, "
                       f"{results['unhealthy_proxies']} unhealthy, "
                       f"{results['blacklisted_proxies']} blacklisted")
            
            return results
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get comprehensive statistics.
        
        Returns:
            Dictionary with all proxy statistics
        """
        with self.lock:
            stats_dict = {}
            
            for proxy in self.proxies:
                proxy_stats = [
                    (gw, stats) for (p, gw), stats in self.stats.items()
                    if p == proxy
                ]
                
                if not proxy_stats:
                    continue
                
                total_requests = sum(stats.total_requests for _, stats in proxy_stats)
                total_successes = sum(stats.successful_requests for _, stats in proxy_stats)
                total_failures = sum(stats.failed_requests for _, stats in proxy_stats)
                
                stats_dict[proxy] = {
                    "total_requests": total_requests,
                    "successful_requests": total_successes,
                    "failed_requests": total_failures,
                    "success_rate": f"{(total_successes / total_requests * 100) if total_requests > 0 else 100:.1f}%",
                    "gateway_breakdown": [
                        {
                            "gateway": gw,
                            "requests": stats.total_requests,
                            "success_rate": f"{stats.success_rate:.1f}%",
                            "status": stats.status.value
                        }
                        for gw, stats in sorted(proxy_stats, key=lambda x: x[0])
                    ]
                }
            
            return {
                "timestamp": time.time(),
                "proxies": stats_dict,
                "last_health_check": self.last_health_check
            }
    
    def print_stats(self) -> None:
        """Print formatted proxy statistics."""
        with self.lock:
            print("\n" + "="*80)
            print("PROXY ROTATION STATISTICS")
            print("="*80)
            
            for proxy in self.proxies:
                proxy_stats = [
                    (gw, stats) for (p, gw), stats in self.stats.items()
                    if p == proxy
                ]
                
                if not proxy_stats:
                    continue
                
                print(f"\nProxy: {proxy}")
                print("-" * 80)
                
                for gw, stats in sorted(proxy_stats, key=lambda x: x[0]):
                    print(f"  {stats}")
            
            # Summary
            print("\n" + "="*80)
            total_requests = sum(
                stats.total_requests for stats in self.stats.values()
            )
            total_successes = sum(
                stats.successful_requests for stats in self.stats.values()
            )
            
            if total_requests > 0:
                overall_rate = (total_successes / total_requests) * 100
                print(f"Overall Success Rate: {overall_rate:.1f}% ({total_successes}/{total_requests})")
            
            print("="*80 + "\n")
    
    def reset_stats(self, proxy: Optional[str] = None, gateway: Optional[str] = None) -> None:
        """
        Reset statistics for specific proxy/gateway combination.
        
        Args:
            proxy: Proxy URL (all if None)
            gateway: Gateway name (all if None)
        """
        with self.lock:
            if proxy is None and gateway is None:
                # Reset all
                for stats in self.stats.values():
                    stats.total_requests = 0
                    stats.successful_requests = 0
                    stats.failed_requests = 0
                    stats.consecutive_failures = 0
                    stats.status = ProxyStatus.HEALTHY
                logger.info("All proxy statistics reset")
            else:
                # Reset specific
                for (p, gw), stats in self.stats.items():
                    if (proxy is None or p == proxy) and (gateway is None or gw == gateway):
                        stats.total_requests = 0
                        stats.successful_requests = 0
                        stats.failed_requests = 0
                        stats.consecutive_failures = 0
                        stats.status = ProxyStatus.HEALTHY
                logger.info(f"Reset stats for proxy={proxy}, gateway={gateway}")


# Global rotator instance
_rotator = ProxyRotator()


def get_rotator() -> ProxyRotator:
    """Get global proxy rotator instance."""
    return _rotator


if __name__ == "__main__":
    # Example usage
    rotator = ProxyRotator()
    
    # Simulate proxy usage
    print("Simulating proxy rotation...")
    
    for i in range(50):
        proxy = rotator.get_next_proxy(gateway="charge1")
        
        # Simulate success/failure
        if random.random() > 0.15:  # 85% success rate
            rotator.mark_proxy_success(proxy, gateway="charge1")
        else:
            rotator.mark_proxy_failure(proxy, gateway="charge1")
    
    # Print stats
    rotator.print_stats()
    
    # Health check
    health = rotator.run_health_check()
    print(f"Health Check Results: {health}")
