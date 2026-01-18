"""
Gateway Health Check Utilities
Provides standardized health checking for all gateways
"""

import requests
import time
from typing import Tuple, Optional, Dict, Any


def basic_health_check(
    test_url: str,
    timeout: int = 5,
    expected_status: int = 200,
    method: str = 'GET',
    **kwargs
) -> Tuple[bool, float, int]:
    """
    Perform a basic health check on a URL
    
    Args:
        test_url: URL to test
        timeout: Request timeout in seconds
        expected_status: Expected HTTP status code
        method: HTTP method (GET, POST, HEAD)
        **kwargs: Additional arguments to pass to requests
    
    Returns:
        Tuple of (is_healthy, response_time_sec, status_code)
    """
    try:
        start = time.time()
        if method.upper() == 'HEAD':
            response = requests.head(test_url, timeout=timeout, **kwargs)
        elif method.upper() == 'POST':
            response = requests.post(test_url, timeout=timeout, **kwargs)
        else:
            response = requests.get(test_url, timeout=timeout, **kwargs)
        elapsed = time.time() - start
        
        is_healthy = response.status_code == expected_status
        return is_healthy, elapsed, response.status_code
    except (requests.Timeout, requests.ConnectionError, requests.RequestException):
        return False, 0.0, 0


def stripe_health_check(timeout: int = 5) -> bool:
    """Check Stripe API connectivity"""
    url = "https://api.stripe.com/v1/charge"  # This will 401 but proves connectivity
    try:
        response = requests.get(url, timeout=timeout)
        # Stripe returns 401 without auth, but that means the API is up
        return response.status_code in [401, 403, 400]
    except Exception:
        return False


def paypal_health_check(timeout: int = 5) -> bool:
    """Check PayPal API connectivity"""
    url = "https://www.paypal.com/graphql"
    try:
        # Attempt to get the GraphQL endpoint
        response = requests.get(url, timeout=timeout)
        return response.status_code in [200, 405, 400]  # 405 = Method Not Allowed, but endpoint exists
    except Exception:
        return False


def shopify_health_check(timeout: int = 5) -> bool:
    """Check Shopify API connectivity with a known store"""
    url = "https://shopzone.nz/products.json?limit=1"
    try:
        response = requests.get(url, timeout=timeout, verify=False)
        return response.status_code == 200
    except Exception:
        return False


def braintree_health_check(timeout: int = 5) -> bool:
    """Check Braintree API connectivity"""
    url = "https://api.braintreegateway.com/"
    try:
        response = requests.get(url, timeout=timeout)
        # Braintree will return 403 or 401 without proper auth
        return response.status_code in [400, 401, 403]
    except Exception:
        return False


def generic_gateway_health_check(
    gateway_name: str,
    test_url: str,
    timeout: int = 5
) -> bool:
    """
    Generic health check for any gateway
    
    Args:
        gateway_name: Name of the gateway (for logging)
        test_url: URL to test
        timeout: Timeout in seconds
    
    Returns:
        True if gateway is reachable
    """
    try:
        response = requests.get(test_url, timeout=timeout, verify=False)
        return response.status_code < 500  # Anything other than 5xx is acceptable
    except Exception:
        return False


class GatewayHealthMonitor:
    """Monitor health of multiple gateways"""
    
    def __init__(self):
        self.last_check = {}
        self.check_interval = 300  # Check every 5 minutes
        self.results = {}
    
    def should_recheck(self, gateway_name: str) -> bool:
        """Check if gateway needs a health check"""
        if gateway_name not in self.last_check:
            return True
        elapsed = time.time() - self.last_check[gateway_name]
        return elapsed > self.check_interval
    
    def check_gateway(self, gateway_name: str, check_fn) -> bool:
        """
        Check a single gateway
        
        Args:
            gateway_name: Name of the gateway
            check_fn: Callable that returns True/False for health
        
        Returns:
            Health status (True = healthy)
        """
        if not self.should_recheck(gateway_name):
            return self.results.get(gateway_name, False)
        
        try:
            is_healthy = check_fn()
            self.results[gateway_name] = is_healthy
            self.last_check[gateway_name] = time.time()
            return is_healthy
        except Exception:
            self.results[gateway_name] = False
            self.last_check[gateway_name] = time.time()
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all monitored gateways"""
        return {
            'results': self.results,
            'last_updated': self.last_check,
            'healthy_count': sum(1 for v in self.results.values() if v),
            'total_count': len(self.results)
        }


# Global health monitor instance
_monitor = None

def get_monitor() -> GatewayHealthMonitor:
    """Get or create the global health monitor"""
    global _monitor
    if _monitor is None:
        _monitor = GatewayHealthMonitor()
    return _monitor
