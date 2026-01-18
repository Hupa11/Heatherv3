"""
HTTP Connection Pool Manager using httpx
Provides efficient connection pooling and async request handling
"""

import httpx
import asyncio
import time
from typing import Dict, Optional, Any, Union
from dataclasses import dataclass
from contextlib import asynccontextmanager

from gates.stealth import get_random_headers, StealthSession


@dataclass
class PoolConfig:
    """Configuration for HTTP connection pool"""
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 20.0
    write_timeout: float = 10.0
    pool_timeout: float = 10.0


# Global pool instances
_sync_clients: Dict[str, httpx.Client] = {}
_async_clients: Dict[str, httpx.AsyncClient] = {}

# Default configuration
_default_config = PoolConfig()


def get_sync_client(
    pool_name: str = "default",
    proxy: Optional[str] = None,
    config: Optional[PoolConfig] = None
) -> httpx.Client:
    """
    Get or create a synchronous HTTP client with connection pooling.
    
    Args:
        pool_name: Name for this pool (use different names for different proxy configs)
        proxy: Optional proxy URL
        config: Optional pool configuration
    
    Returns:
        httpx.Client with connection pooling
    """
    cfg = config or _default_config
    key = f"{pool_name}_{proxy or 'direct'}"
    
    if key not in _sync_clients:
        limits = httpx.Limits(
            max_connections=cfg.max_connections,
            max_keepalive_connections=cfg.max_keepalive_connections,
            keepalive_expiry=cfg.keepalive_expiry,
        )
        
        timeout = httpx.Timeout(
            connect=cfg.connect_timeout,
            read=cfg.read_timeout,
            write=cfg.write_timeout,
            pool=cfg.pool_timeout,
        )
        
        proxy_config = None
        if proxy:
            proxy_config = proxy
        
        _sync_clients[key] = httpx.Client(
            limits=limits,
            timeout=timeout,
            proxy=proxy_config,
            verify=False,
            follow_redirects=True,
            http2=True,
        )
    
    return _sync_clients[key]


async def get_async_client(
    pool_name: str = "default",
    proxy: Optional[str] = None,
    config: Optional[PoolConfig] = None
) -> httpx.AsyncClient:
    """
    Get or create an asynchronous HTTP client with connection pooling.
    
    Args:
        pool_name: Name for this pool
        proxy: Optional proxy URL
        config: Optional pool configuration
    
    Returns:
        httpx.AsyncClient with connection pooling
    """
    cfg = config or _default_config
    key = f"{pool_name}_{proxy or 'direct'}"
    
    if key not in _async_clients:
        limits = httpx.Limits(
            max_connections=cfg.max_connections,
            max_keepalive_connections=cfg.max_keepalive_connections,
            keepalive_expiry=cfg.keepalive_expiry,
        )
        
        timeout = httpx.Timeout(
            connect=cfg.connect_timeout,
            read=cfg.read_timeout,
            write=cfg.write_timeout,
            pool=cfg.pool_timeout,
        )
        
        proxy_config = None
        if proxy:
            proxy_config = proxy
        
        _async_clients[key] = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            proxy=proxy_config,
            verify=False,
            follow_redirects=True,
            http2=True,
        )
    
    return _async_clients[key]


def pooled_request(
    method: str,
    url: str,
    pool_name: str = "default",
    proxy: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    use_stealth: bool = True,
    referer: Optional[str] = None,
    origin: Optional[str] = None,
) -> httpx.Response:
    """
    Make a synchronous HTTP request using connection pooling.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        pool_name: Pool name for connection reuse
        proxy: Optional proxy URL
        headers: Optional custom headers
        data: Optional form data
        json: Optional JSON data
        timeout: Optional timeout override
        use_stealth: Whether to use stealth headers
        referer: Optional referer for stealth headers
        origin: Optional origin for stealth headers
    
    Returns:
        httpx.Response object
    """
    client = get_sync_client(pool_name, proxy)
    
    # Build headers
    if use_stealth:
        request_headers = get_random_headers(referer=referer, origin=origin, api_mode=bool(data or json))
    else:
        request_headers = {}
    
    if headers:
        request_headers.update(headers)
    
    # Make request
    kwargs = {"headers": request_headers}
    if data:
        kwargs["data"] = data
    if json:
        kwargs["json"] = json
    if timeout:
        kwargs["timeout"] = timeout
    
    return client.request(method, url, **kwargs)


async def async_pooled_request(
    method: str,
    url: str,
    pool_name: str = "default",
    proxy: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    use_stealth: bool = True,
    referer: Optional[str] = None,
    origin: Optional[str] = None,
) -> httpx.Response:
    """
    Make an asynchronous HTTP request using connection pooling.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        pool_name: Pool name for connection reuse
        proxy: Optional proxy URL
        headers: Optional custom headers
        data: Optional form data
        json: Optional JSON data
        timeout: Optional timeout override
        use_stealth: Whether to use stealth headers
        referer: Optional referer for stealth headers
        origin: Optional origin for stealth headers
    
    Returns:
        httpx.Response object
    """
    client = await get_async_client(pool_name, proxy)
    
    # Build headers
    if use_stealth:
        request_headers = get_random_headers(referer=referer, origin=origin, api_mode=bool(data or json))
    else:
        request_headers = {}
    
    if headers:
        request_headers.update(headers)
    
    # Make request
    kwargs = {"headers": request_headers}
    if data:
        kwargs["data"] = data
    if json:
        kwargs["json"] = json
    if timeout:
        kwargs["timeout"] = timeout
    
    return await client.request(method, url, **kwargs)


class PooledSession:
    """
    A session-like interface for making pooled requests with consistent stealth profile.
    """
    
    def __init__(
        self,
        pool_name: str = "default",
        proxy: Optional[str] = None,
        config: Optional[PoolConfig] = None,
    ):
        self.pool_name = pool_name
        self.proxy = proxy
        self.config = config or _default_config
        self.stealth = StealthSession()
        self.request_count = 0
        self.last_request_time = 0.0
    
    def get(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request"""
        return self._request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> httpx.Response:
        """Make POST request"""
        return self._request("POST", url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Internal request method"""
        # Add delay if needed
        self.stealth.pre_request_delay()
        
        # Get headers from stealth session
        referer = kwargs.pop("referer", None)
        origin = kwargs.pop("origin", None)
        api_mode = bool(kwargs.get("data") or kwargs.get("json"))
        
        headers = self.stealth.get_headers(referer=referer, origin=origin, api_mode=api_mode)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        # Make request
        response = pooled_request(
            method, url,
            pool_name=self.pool_name,
            proxy=self.proxy,
            headers=headers,
            use_stealth=False,  # We already added stealth headers
            **kwargs
        )
        
        # Update timing
        self.stealth.post_request()
        self.request_count += 1
        
        # Rotate profile if needed
        if self.stealth.should_rotate_profile():
            self.stealth.rotate_profile()
        
        return response


async def close_all_pools():
    """Close all connection pools"""
    for client in _sync_clients.values():
        client.close()
    _sync_clients.clear()
    
    for client in _async_clients.values():
        await client.aclose()
    _async_clients.clear()


def close_sync_pools():
    """Close all synchronous connection pools"""
    for client in _sync_clients.values():
        client.close()
    _sync_clients.clear()


def get_pool_stats() -> Dict[str, Any]:
    """Get statistics about connection pools"""
    return {
        "sync_pools": len(_sync_clients),
        "async_pools": len(_async_clients),
        "pool_names": list(_sync_clients.keys()) + list(_async_clients.keys()),
    }
