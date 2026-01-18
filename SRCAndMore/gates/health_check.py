"""
Store Health Check Module - Background health monitoring and session caching
Periodically checks store status and caches checkout sessions for faster checks
"""

import asyncio
import time
import random
import httpx
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import logging

logger = logging.getLogger(__name__)


class StoreHealth(Enum):
    """Health status of a store"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class CachedSession:
    """Cached checkout session data for a store"""
    store_domain: str
    storefront_token: str
    checkout_token: Optional[str] = None
    checkout_url: Optional[str] = None
    product_id: Optional[str] = None
    product_price: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    
    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 1800
    
    @property
    def is_valid(self) -> bool:
        """Check if session is still valid"""
        return time.time() < self.expires_at
    
    @property
    def age_seconds(self) -> float:
        """How old is this session"""
        return time.time() - self.created_at


@dataclass 
class StoreHealthStatus:
    """Health status for a store"""
    domain: str
    health: StoreHealth = StoreHealth.UNKNOWN
    last_check: float = 0.0
    response_time_ms: float = 0.0
    error_count: int = 0
    success_count: int = 0
    last_error: str = ""
    cached_session: Optional[CachedSession] = None
    
    @property
    def success_rate(self) -> float:
        total = self.error_count + self.success_count
        if total == 0:
            return 0.5
        return self.success_count / total
    
    def record_success(self, response_time_ms: float) -> None:
        """Record successful health check"""
        self.success_count += 1
        self.last_check = time.time()
        self.response_time_ms = response_time_ms
        self.last_error = ""
        
        if self.success_rate >= 0.8:
            self.health = StoreHealth.HEALTHY
        elif self.success_rate >= 0.5:
            self.health = StoreHealth.DEGRADED
        else:
            self.health = StoreHealth.UNHEALTHY
    
    def record_failure(self, error: str) -> None:
        """Record failed health check"""
        self.error_count += 1
        self.last_check = time.time()
        self.last_error = error
        
        if self.success_rate < 0.3:
            self.health = StoreHealth.UNHEALTHY
        elif self.success_rate < 0.7:
            self.health = StoreHealth.DEGRADED


class SessionCache:
    """
    Caches checkout sessions and storefront tokens per store.
    Sessions are valid for ~30 minutes, saving 2 API calls per check.
    """
    
    def __init__(self, max_age: float = 1800):
        self._cache: Dict[str, CachedSession] = {}
        self._max_age = max_age
        self._lock = threading.Lock()
    
    def get(self, domain: str) -> Optional[CachedSession]:
        """Get cached session if valid"""
        with self._lock:
            if domain in self._cache:
                session = self._cache[domain]
                if session.is_valid:
                    return session
                else:
                    del self._cache[domain]
        return None
    
    def set(self, session: CachedSession) -> None:
        """Cache a session"""
        with self._lock:
            self._cache[session.store_domain] = session
    
    def invalidate(self, domain: str) -> bool:
        """Invalidate cached session for a domain"""
        with self._lock:
            if domain in self._cache:
                del self._cache[domain]
                return True
        return False
    
    def clear_expired(self) -> int:
        """Clear all expired sessions"""
        with self._lock:
            expired = [d for d, s in self._cache.items() if not s.is_valid]
            for domain in expired:
                del self._cache[domain]
            return len(expired)
    
    def clear_all(self) -> int:
        """Clear all cached sessions"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            valid = sum(1 for s in self._cache.values() if s.is_valid)
            return {
                "total_cached": len(self._cache),
                "valid_sessions": valid,
                "expired_sessions": len(self._cache) - valid,
            }


class StoreHealthChecker:
    """
    Background health checker for stores.
    Periodically pings stores to maintain fresh status data.
    """
    
    def __init__(
        self,
        check_interval: float = 300,
        timeout: float = 10,
        max_concurrent: int = 5
    ):
        self.check_interval = check_interval
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        
        self._stores: Dict[str, StoreHealthStatus] = {}
        self._session_cache = SessionCache()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
    
    def add_store(self, domain: str) -> None:
        """Add store to health monitoring"""
        with self._lock:
            if domain not in self._stores:
                self._stores[domain] = StoreHealthStatus(domain=domain)
    
    def remove_store(self, domain: str) -> bool:
        """Remove store from health monitoring"""
        with self._lock:
            if domain in self._stores:
                del self._stores[domain]
                self._session_cache.invalidate(domain)
                return True
        return False
    
    def get_health(self, domain: str) -> StoreHealthStatus:
        """Get health status for a store"""
        with self._lock:
            if domain not in self._stores:
                self._stores[domain] = StoreHealthStatus(domain=domain)
            return self._stores[domain]
    
    def get_cached_session(self, domain: str) -> Optional[CachedSession]:
        """Get cached session for a store"""
        return self._session_cache.get(domain)
    
    def cache_session(self, session: CachedSession) -> None:
        """Cache a checkout session"""
        self._session_cache.set(session)
    
    async def check_store(self, domain: str, proxy: str = None) -> StoreHealthStatus:
        """
        Perform health check on a single store.
        Also attempts to cache the storefront token.
        """
        status = self.get_health(domain)
        start_time = time.time()
        
        url = f"https://{domain}" if not domain.startswith("http") else domain
        
        proxies = None
        if proxy:
            try:
                parts = proxy.split(':')
                if len(parts) == 4:
                    proxies = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                else:
                    proxies = f"http://{parts[0]}:{parts[1]}"
            except Exception:
                pass
        
        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=self.timeout,
                follow_redirects=True,
                verify=False
            ) as client:
                resp = await client.get(f"{url}/products.json?limit=1")
                
                if resp.status_code != 200:
                    status.record_failure(f"HTTP {resp.status_code}")
                    return status
                
                elapsed_ms = (time.time() - start_time) * 1000
                status.record_success(elapsed_ms)
                
                main_resp = await client.get(url)
                
                import re
                token_match = re.search(r'"accessToken":"([^"]+)"', main_resp.text)
                
                if token_match:
                    token = token_match.group(1)
                    
                    products = resp.json().get("products", [])
                    product_id = None
                    product_price = None
                    
                    if products:
                        variants = products[0].get("variants", [])
                        for v in variants:
                            if v.get("available"):
                                product_id = str(v.get("id"))
                                try:
                                    product_price = float(v.get("price", 0))
                                except (ValueError, TypeError):
                                    pass
                                break
                    
                    session = CachedSession(
                        store_domain=domain,
                        storefront_token=token,
                        product_id=product_id,
                        product_price=product_price,
                    )
                    self._session_cache.set(session)
                    status.cached_session = session
                
                return status
                
        except httpx.TimeoutException:
            status.record_failure("Timeout")
        except Exception as e:
            status.record_failure(str(e)[:50])
        
        return status
    
    async def check_all_stores(self, proxy: str = None) -> Dict[str, StoreHealthStatus]:
        """Check health of all registered stores"""
        with self._lock:
            domains = list(self._stores.keys())
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def check_one(domain: str) -> Tuple[str, StoreHealthStatus]:
            async with semaphore:
                status = await self.check_store(domain, proxy)
                return (domain, status)
        
        tasks = [check_one(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        statuses = {}
        for result in results:
            if isinstance(result, tuple):
                domain, status = result
                statuses[domain] = status
        
        return statuses
    
    def get_healthy_stores(self) -> List[str]:
        """Get list of healthy store domains"""
        with self._lock:
            return [d for d, s in self._stores.items() if s.health == StoreHealth.HEALTHY]
    
    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get all store statuses as dicts"""
        with self._lock:
            return {
                domain: {
                    "health": status.health.value,
                    "success_rate": f"{status.success_rate * 100:.1f}%",
                    "response_time_ms": round(status.response_time_ms, 1),
                    "last_error": status.last_error,
                    "has_cached_session": status.cached_session is not None and status.cached_session.is_valid,
                }
                for domain, status in self._stores.items()
            }
    
    async def _health_check_loop(self, proxy: str = None) -> None:
        """Background loop for periodic health checks"""
        while self._running:
            try:
                await self.check_all_stores(proxy)
                self._session_cache.clear_expired()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def start_background_checks(self, proxy: str = None) -> None:
        """Start background health check loop"""
        if self._running:
            return
        
        self._running = True
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._task = asyncio.create_task(self._health_check_loop(proxy))
            else:
                pass
        except RuntimeError:
            pass
    
    def stop_background_checks(self) -> None:
        """Stop background health check loop"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None


class PreWarmManager:
    """
    Pre-warms store sessions before batch checks.
    Visits stores ahead of time to establish sessions and reduce cold-start failures.
    """
    
    def __init__(self, health_checker: StoreHealthChecker):
        self.health_checker = health_checker
    
    async def prewarm_stores(
        self, 
        domains: List[str], 
        count: int = 3,
        proxy: str = None
    ) -> int:
        """
        Pre-warm a number of stores by visiting their pages.
        
        Args:
            domains: List of store domains to potentially warm
            count: Number of stores to warm (default 3)
            proxy: Optional proxy
        
        Returns:
            Number of stores successfully warmed
        """
        to_warm = random.sample(domains, min(count, len(domains)))
        success_count = 0
        
        for domain in to_warm:
            try:
                status = await self.health_checker.check_store(domain, proxy)
                if status.health in [StoreHealth.HEALTHY, StoreHealth.DEGRADED]:
                    success_count += 1
            except Exception:
                pass
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        return success_count
    
    def get_warmed_stores(self) -> List[str]:
        """Get stores that have valid cached sessions"""
        healthy = self.health_checker.get_healthy_stores()
        warmed = []
        
        for domain in healthy:
            session = self.health_checker.get_cached_session(domain)
            if session and session.is_valid:
                warmed.append(domain)
        
        return warmed


_health_checker = StoreHealthChecker()
_prewarm_manager = PreWarmManager(_health_checker)


def add_store_to_health_check(domain: str) -> None:
    """Add store to background health monitoring"""
    _health_checker.add_store(domain)


def get_store_health(domain: str) -> StoreHealthStatus:
    """Get health status for a store"""
    return _health_checker.get_health(domain)


def get_cached_session(domain: str) -> Optional[CachedSession]:
    """Get cached checkout session for faster checks"""
    return _health_checker.get_cached_session(domain)


def cache_checkout_session(session: CachedSession) -> None:
    """Cache a checkout session"""
    _health_checker.cache_session(session)


async def check_store_health(domain: str, proxy: str = None) -> StoreHealthStatus:
    """Perform health check on a store"""
    return await _health_checker.check_store(domain, proxy)


async def check_all_stores_health(proxy: str = None) -> Dict[str, StoreHealthStatus]:
    """Check health of all monitored stores"""
    return await _health_checker.check_all_stores(proxy)


def get_healthy_stores() -> List[str]:
    """Get list of healthy stores"""
    return _health_checker.get_healthy_stores()


def get_all_health_statuses() -> Dict[str, Dict]:
    """Get health statuses for all stores"""
    return _health_checker.get_all_statuses()


async def prewarm_stores(domains: List[str], count: int = 3, proxy: str = None) -> int:
    """Pre-warm stores before batch checks"""
    return await _prewarm_manager.prewarm_stores(domains, count, proxy)


def get_warmed_stores() -> List[str]:
    """Get stores with valid cached sessions"""
    return _prewarm_manager.get_warmed_stores()


def start_health_monitoring(proxy: str = None) -> None:
    """Start background health monitoring"""
    _health_checker.start_background_checks(proxy)


def stop_health_monitoring() -> None:
    """Stop background health monitoring"""
    _health_checker.stop_background_checks()
