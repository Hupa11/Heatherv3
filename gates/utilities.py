"""
Utility APIs Module
BIN Lookup, Fake Address Generation, ChatGPT API,
and shared HTTP timeout/retry/backoff utilities with universal proxy management
"""

import requests
import json
import time
import random
import os
import threading
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

# Standardized HTTP settings for gateways
REQUEST_TIMEOUT = 15  # seconds
RETRY_ATTEMPTS = 3
BACKOFF_INITIAL = 0.5  # seconds
BACKOFF_FACTOR = 2.0
BACKOFF_MAX = 6.0  # cap maximum sleep
BACKOFF_JITTER = 0.25  # random jitter added to backoff

# Status codes we consider retryable on server response
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ============================================================================
# Universal Proxy Manager with Auto-Reconnection
# ============================================================================

@dataclass
class ProxyState:
    """Track global proxy state with thread-safe updates."""
    url: str = ""
    is_alive: bool = False
    last_check: float = 0.0
    consecutive_failures: int = 0
    last_ip: str = ""
    lock: threading.Lock = None
    
    def __post_init__(self):
        if self.lock is None:
            self.lock = threading.Lock()

# Global proxy state
_proxy_state = ProxyState()
_proxy_check_interval = 60  # Check proxy health every 60 seconds
_max_consecutive_failures = 3  # Max failures before forcing reconnect


def parse_proxy(proxy: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Parse various proxy formats into a standardized dict for requests.
    
    Supported formats:
    - None or empty: returns None
    - "IP:PORT:USER:PASS" -> http://USER:PASS@IP:PORT
    - "IP:PORT" -> http://IP:PORT
    - "http://..." or "https://..." -> as-is
    - dict with 'http'/'https' keys -> as-is
    
    Returns:
        Dict with 'http' and 'https' keys, or None
    """
    if not proxy:
        return None
    
    if isinstance(proxy, dict):
        return proxy
    
    proxy = proxy.strip()
    
    if proxy.startswith('http://') or proxy.startswith('https://'):
        return {'http': proxy, 'https': proxy}
    
    parts = proxy.split(':')
    
    if len(parts) == 4:
        ip, port, user, passwd = parts
        proxy_url = f"http://{user}:{passwd}@{ip}:{port}"
    elif len(parts) == 2:
        ip, port = parts
        proxy_url = f"http://{ip}:{port}"
    else:
        proxy_url = f"http://{proxy}"
    
    return {'http': proxy_url, 'https': proxy_url}


def _build_proxy_url() -> Dict[str, str]:
    """Build proxy dict from environment or config."""
    proxy_http = os.getenv('PROXY_HTTP', '')
    proxy_https = os.getenv('PROXY_HTTPS', '')
    
    if not proxy_http:
        residential = os.getenv('RESIDENTIAL_PROXY', '')
        if residential:
            proxy_http = residential
            proxy_https = residential
    
    if not proxy_http:
        return {'http': '', 'https': ''}
    
    return {
        'http': proxy_http,
        'https': proxy_https or proxy_http
    }


def check_proxy_health(proxy_dict: Optional[Dict[str, str]] = None, timeout: int = 10) -> Tuple[bool, str]:
    """
    Check if proxy is alive and get the external IP.
    
    Returns:
        (is_alive: bool, ip_address: str)
    """
    if proxy_dict is None:
        proxy_dict = _build_proxy_url()
    
    try:
        response = requests.get(
            'https://api.ipify.org?format=json',
            proxies=proxy_dict,
            timeout=timeout,
            verify=False
        )
        if response.status_code == 200:
            ip = response.json().get('ip', 'Unknown')
            return True, ip
    except (requests.exceptions.ProxyError, requests.exceptions.Timeout, 
            requests.exceptions.ConnectionError, Exception):
        pass
    
    return False, ""


def get_proxy(force_check: bool = False) -> Dict[str, str]:
    """
    Get the current proxy config with auto-health check and reconnection.
    
    This function:
    1. Returns cached proxy if recently checked and healthy
    2. Verifies proxy health periodically
    3. Auto-reconnects if proxy is dead (by rotating IP when supported)
    
    Args:
        force_check: If True, always perform health check
    
    Returns:
        Dict with 'http' and 'https' proxy URLs
    """
    global _proxy_state
    
    with _proxy_state.lock:
        current_time = time.time()
        proxy_dict = _build_proxy_url()
        
        # Check if we need to verify proxy health
        should_check = (
            force_check or
            not _proxy_state.is_alive or
            _proxy_state.consecutive_failures >= _max_consecutive_failures or
            (current_time - _proxy_state.last_check) > _proxy_check_interval
        )
        
        if should_check:
            is_alive, ip = check_proxy_health(proxy_dict)
            
            _proxy_state.last_check = current_time
            _proxy_state.url = proxy_dict.get('http', '')
            
            if is_alive:
                _proxy_state.is_alive = True
                _proxy_state.consecutive_failures = 0
                _proxy_state.last_ip = ip
            else:
                _proxy_state.is_alive = False
                _proxy_state.consecutive_failures += 1
                
                # Try to reconnect by waiting and checking again
                if _proxy_state.consecutive_failures >= _max_consecutive_failures:
                    # Wait and retry once more (proxy rotation)
                    time.sleep(2)
                    is_alive, ip = check_proxy_health(proxy_dict)
                    if is_alive:
                        _proxy_state.is_alive = True
                        _proxy_state.consecutive_failures = 0
                        _proxy_state.last_ip = ip
        
        return proxy_dict


def mark_proxy_success() -> None:
    """Mark the current proxy request as successful."""
    global _proxy_state
    with _proxy_state.lock:
        _proxy_state.is_alive = True
        _proxy_state.consecutive_failures = 0


def mark_proxy_failure() -> None:
    """Mark the current proxy request as failed."""
    global _proxy_state
    with _proxy_state.lock:
        _proxy_state.consecutive_failures += 1
        if _proxy_state.consecutive_failures >= _max_consecutive_failures:
            _proxy_state.is_alive = False


def get_proxy_status() -> Dict:
    """Get current proxy status for diagnostics."""
    global _proxy_state
    with _proxy_state.lock:
        return {
            'is_alive': _proxy_state.is_alive,
            'last_ip': _proxy_state.last_ip,
            'consecutive_failures': _proxy_state.consecutive_failures,
            'last_check': _proxy_state.last_check,
            'url': _proxy_state.url[:50] + '...' if len(_proxy_state.url) > 50 else _proxy_state.url
        }


def apply_proxy_to_session(session: requests.Session, proxy: Optional[str] = None) -> str:
    """
    Apply proxy to a requests session with auto-reconnection.
    
    Args:
        session: requests.Session to configure
        proxy: Optional proxy string (uses global proxy if None)
    
    Returns:
        Proxy status string ("Yes" if alive, "No" if not)
    """
    if proxy:
        # Parse custom proxy format (ip:port:user:pass or ip:port)
        try:
            parts = proxy.split(":")
            if len(parts) == 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif len(parts) >= 2:
                proxy_url = f"http://{parts[0]}:{parts[1]}"
            else:
                proxy_url = proxy
            
            session.proxies.update({'http': proxy_url, 'https': proxy_url})
            
            # Quick health check
            is_alive, _ = check_proxy_health({'http': proxy_url, 'https': proxy_url}, timeout=5)
            return "Yes" if is_alive else "No"
        except Exception:
            pass
    
    # Use global proxy with auto-reconnection
    proxy_dict = get_proxy()
    session.proxies.update(proxy_dict)
    
    return "Yes" if _proxy_state.is_alive else "No"


def http_request(
    method: str,
    url: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: Optional[int] = None,
    retries: Optional[int] = None,
    backoff_initial: float = BACKOFF_INITIAL,
    backoff_factor: float = BACKOFF_FACTOR,
    backoff_max: float = BACKOFF_MAX,
    jitter: float = BACKOFF_JITTER,
    retry_on_status: Optional[set] = None,
    on_rate_limit=None,  # Callable to notify on rate limit (429)
    on_service_unavailable=None,  # Callable to notify on 503
    use_proxy: bool = False,  # Enable proxy with auto-reconnection
    **kwargs,
):
    """
    Perform an HTTP request with exponential backoff, jitter, and optional proxy.

    - Retries on network errors (timeout/connection) and retryable status codes.
    - Calls on_rate_limit callback if 429 status detected.
    - Calls on_service_unavailable callback if 503 status detected.
    - If use_proxy=True, automatically uses global proxy with reconnection on failure.
    - Returns the final response (even if non-2xx) unless a network error persists.
    - Raises the last exception only if all retries fail due to network errors.
    """
    sess = session or requests
    t = REQUEST_TIMEOUT if timeout is None else timeout
    attempts = RETRY_ATTEMPTS if retries is None else retries
    retry_status = RETRYABLE_STATUS if retry_on_status is None else retry_on_status
    
    # Apply proxy if requested and not already set
    if use_proxy and 'proxies' not in kwargs:
        kwargs['proxies'] = get_proxy()

    last_exc = None
    proxy_retry_done = False
    
    for attempt in range(attempts):
        try:
            resp = sess.request(method.upper(), url, timeout=t, **kwargs)
            
            # Mark proxy success on any valid response
            if use_proxy and resp.status_code < 500:
                mark_proxy_success()
            
            # Handle rate limit (429) with extended backoff
            if resp.status_code == 429:
                if on_rate_limit:
                    on_rate_limit()
                if attempt < attempts - 1:
                    time.sleep(60)
                    continue
                return resp
            # Handle service unavailable (503)
            if resp.status_code == 503:
                if on_service_unavailable:
                    on_service_unavailable()
                if attempt < attempts - 1:
                    time.sleep(30)
                    continue
                return resp
            # If status is retryable, backoff and try again (unless last attempt)
            if resp.status_code in retry_status and attempt < attempts - 1:
                sleep_s = min(backoff_initial * (backoff_factor ** attempt) + random.uniform(0, jitter), backoff_max)
                time.sleep(sleep_s)
                continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.ProxyError) as e:
            last_exc = e
            
            # Mark proxy failure and try to reconnect
            if use_proxy:
                mark_proxy_failure()
                if not proxy_retry_done:
                    # Force proxy health check and reconnection
                    kwargs['proxies'] = get_proxy(force_check=True)
                    proxy_retry_done = True
            
            if attempt >= attempts - 1:
                raise
            sleep_s = min(backoff_initial * (backoff_factor ** attempt) + random.uniform(0, jitter), backoff_max)
            time.sleep(sleep_s)

    # If we reach here, raise last exception if available
    if last_exc:
        raise last_exc
    # Fallback shouldn't be hit; but to satisfy typing, perform one last try
    return sess.request(method.upper(), url, timeout=t, **kwargs)

def bin_lookup(bin_code):
    """
    Look up BIN details from antipublic API
    Returns: dict with card info or None
    """
    try:
        response = http_request(
            'GET',
            f"https://bins.antipublic.cc/bins/{bin_code}",
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


def get_fake_address(country_code='us'):
    """
    Generate fake address from randomuser API
    Returns: dict with name, email, address, city, state, zip, phone
    """
    try:
        response = http_request(
            'GET',
            f"https://randomuser.me/api/?nat={country_code}",
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 200:
            data = response.json()
            if 'results' in data and len(data['results']) > 0:
                user = data['results'][0]
                return {
                    'first_name': user['name']['first'],
                    'last_name': user['name']['last'],
                    'email': user['email'],
                    'phone': user['phone'],
                    'street': user['location']['street']['name'],
                    'city': user['location']['city'],
                    'state': user['location']['state'],
                    'zip': user['location']['postcode'],
                    'country': user['location']['country'],
                }
        return None
    except:
        return None


def generate_cc_bulk(bin_code, count=10):
    """
    Generate CC numbers from a BIN using drlabapis
    Returns: list of generated cards
    """
    try:
        url = f"https://drlabapis.onrender.com/api/ccgenerator?bin={bin_code}&count={count}"
        response = http_request('GET', url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            cards = response.text.strip().split('\n')
            return cards
        return []
    except:
        return []


def chatgpt_ask(prompt):
    """
    Get response from ChatGPT API
    Returns: response text
    """
    try:
        url = f"https://api-chatgpt4.eternalowner06.workers.dev/?prompt={prompt}"
        response = http_request('GET', url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            return data.get('message', '')
        return None
    except:
        return None
