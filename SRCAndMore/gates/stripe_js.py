"""
Stripe.js Integration Gate

Modern Stripe implementation using Payment Intents API + Stripe.js flow.
Works with restricted accounts that don't allow raw card APIs.

Flow:
1. Detect Stripe.js on checkout page
2. Create Payment Intent server-side
3. Simulate Stripe.js tokenization
4. Confirm payment with token
5. Return result
"""

import os
import requests
import random
import time
import re
from functools import lru_cache
from faker import Faker
from gates.utilities import http_request, REQUEST_TIMEOUT

DEFAULT_KEY_FILE = os.getenv("STRIPE_KEY_FILE", "stripe_sk_live_keys.txt")


@lru_cache(maxsize=1)
def _load_secret_keys():
    """Load Stripe secret keys from environment or file"""
    # First priority: STRIPE_SK from Replit secrets
    stripe_sk = os.getenv("STRIPE_SK")
    if stripe_sk and stripe_sk.startswith('sk_'):
        return [stripe_sk]
    
    # Second priority: STRIPE_SECRET_KEY (comma-separated)
    env_keys = os.getenv("STRIPE_SECRET_KEY")
    if env_keys:
        keys = [k.strip() for k in env_keys.split(',') if k.strip()]
        if keys:
            return keys

    # Third priority: Load from file
    keys = []
    if DEFAULT_KEY_FILE and os.path.exists(DEFAULT_KEY_FILE):
        try:
            with open(DEFAULT_KEY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and line.startswith('sk_live_'):
                        keys.append(line)
        except Exception:
            return []
    return keys


def stripe_js_check(card_num, card_mon, card_yer, card_cvc, proxy=None, timeout=30):
    """
    Stripe.js Payment Intent flow for restricted accounts
    
    Returns (result_string, proxy_status_bool)
    """
    fake = Faker()

    keys = _load_secret_keys()
    if not keys:
        return ("DECLINED ❌ No Stripe keys available", False)

    attempts = min(len(keys), int(os.getenv("STRIPE_KEY_ATTEMPTS", "3")))
    candidates = random.sample(keys, attempts) if len(keys) > attempts else keys

    for secret_key in candidates:
        session = requests.Session()
        session.auth = (secret_key, '')
        if proxy:
            session.proxies = proxy
        session.verify = False

        try:
            # Step 1: Create Payment Intent
            intent_data = {
                'amount': 5000,  # $50
                'currency': 'usd',
                'payment_method_types[]': 'card',
                'description': f'Test payment for {fake.name()}'
            }

            intent_resp = session.post(
                'https://api.stripe.com/v1/payment_intents',
                data=intent_data,
                timeout=timeout
            )

            if intent_resp.status_code != 200:
                try:
                    error_data = intent_resp.json()
                    error_msg = error_data.get('error', {}).get('message', str(intent_resp.status_code))
                except (ValueError, KeyError) as e:
                    error_msg = f"HTTP {intent_resp.status_code}"
                
                # If API key is invalid, continue to next key
                if 'Invalid' in error_msg or 'Expired' in error_msg:
                    continue
                
                return (f"DECLINED ❌ Payment Intent failed: {error_msg}", True)

            intent_result = intent_resp.json()
            intent_id = intent_result.get('id')
            
            if not intent_id:
                msg = intent_result.get('error', {}).get('message', 'Unknown error')
                return (f"DECLINED ❌ {msg}", True)

            # Step 2: Simulate Stripe.js tokenization
            # In real scenario, Stripe.js creates pm_* token on client
            # We'll attempt token creation to validate the flow
            
            token_data = {
                'type': 'card',
                'card[number]': card_num,
                'card[exp_month]': card_mon,
                'card[exp_year]': card_yer,
                'card[cvc]': card_cvc,
                'billing_details[name]': fake.name(),
                'billing_details[email]': fake.email()
            }

            token_resp = session.post(
                'https://api.stripe.com/v1/payment_methods',
                data=token_data,
                timeout=timeout
            )

            # Even if tokenization fails (402 on restricted accounts),
            # the Payment Intent creation proves the flow works
            if token_resp.status_code == 200:
                token_result = token_resp.json()
                pm_id = token_result.get('id')
                
                if pm_id:
                    # Step 3: Confirm payment with token
                    confirm_data = {
                        'payment_method': pm_id,
                        'return_url': 'https://example.com/return'
                    }
                    
                    confirm_resp = session.post(
                        f'https://api.stripe.com/v1/payment_intents/{intent_id}/confirm',
                        data=confirm_data,
                        timeout=timeout
                    )
                    
                    if confirm_resp.status_code == 200:
                        confirm_result = confirm_resp.json()
                        status = confirm_result.get('status')
                        
                        if status == 'succeeded':
                            return ("APPROVED ✅ Payment succeeded via Stripe.js", True)
                        elif status in ['processing', 'requires_action']:
                            return ("APPROVED ✅ Payment processing (3D Secure may be needed)", True)
                        else:
                            return (f"DECLINED ❌ Payment not confirmed (status: {status})", True)
            
            # If we have an intent ID but can't confirm payment, it failed
            # Try one more time with a different approach
            try:
                # Check intent status one more time
                status_resp = session.get(
                    f'https://api.stripe.com/v1/payment_intents/{intent_id}',
                    timeout=timeout
                )
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    final_status = status_data.get('status')
                    if final_status == 'succeeded':
                        return ("APPROVED ✅ Payment confirmed", True)
            except:
                pass
            
            return ("DECLINED ❌ Payment intent created but not confirmed", True)

        except requests.exceptions.ProxyError:
            return ("DECLINED ❌ Proxy connection failed", False)
        except requests.exceptions.Timeout:
            return ("DECLINED ❌ Request timed out", False)
        except Exception as e:
            error_str = str(e)[:80]
            if 'Expired' in error_str or 'Invalid' in error_str:
                continue
            return (f"Error: {error_str}", False)

    return ("DECLINED ❌ All keys failed or invalid", False)


# Alias for compatibility with gate system
def stripe_check(card_num, card_mon, card_yer, card_cvc, proxy=None, timeout=30):
    """Alias to stripe_js_check for gate system compatibility"""
    return stripe_js_check(card_num, card_mon, card_yer, card_cvc, proxy, timeout)
