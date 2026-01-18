"""
Enhanced Response Parser with Detailed Decline Codes and Confidence Scores
Provides standardized parsing across all gateways
"""

import re
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class CardStatus(Enum):
    """Possible card statuses"""
    LIVE = "live"                   # Card is valid and charged/authorized
    CCN = "ccn"                     # Card number valid, needs CVV
    CVV_MISMATCH = "cvv_mismatch"   # CVV verification failed
    INSUFFICIENT = "insufficient"   # Insufficient funds
    EXPIRED = "expired"             # Card expired
    INVALID = "invalid"             # Invalid card number
    DECLINED = "declined"           # Generic decline
    THREE_DS = "3ds"                # 3D Secure required
    RISK = "risk"                   # Risk/fraud check failed
    RATE_LIMITED = "rate_limited"   # Too many requests
    ERROR = "error"                 # Gateway error
    TIMEOUT = "timeout"             # Request timeout
    UNKNOWN = "unknown"             # Unknown status


@dataclass
class ParsedResponse:
    """Parsed gateway response with detailed information"""
    status: CardStatus
    confidence: float           # 0.0 to 1.0 confidence in the result
    raw_message: str            # Original response message
    decline_code: Optional[str] # Processor decline code if available
    decline_reason: Optional[str]  # Human-readable decline reason
    is_retryable: bool          # Whether request can be retried
    gateway_name: Optional[str] # Gateway that processed this
    
    @property
    def is_live(self) -> bool:
        return self.status == CardStatus.LIVE
    
    @property
    def is_ccn(self) -> bool:
        return self.status == CardStatus.CCN
    
    @property
    def is_dead(self) -> bool:
        return self.status in [
            CardStatus.DECLINED, CardStatus.INVALID, 
            CardStatus.EXPIRED, CardStatus.RISK
        ]
    
    @property
    def emoji(self) -> str:
        """Get status emoji"""
        return {
            CardStatus.LIVE: "✅",
            CardStatus.CCN: "🔵",
            CardStatus.CVV_MISMATCH: "⚠️",
            CardStatus.INSUFFICIENT: "💰",
            CardStatus.EXPIRED: "📅",
            CardStatus.INVALID: "❌",
            CardStatus.DECLINED: "❌",
            CardStatus.THREE_DS: "🔐",
            CardStatus.RISK: "🚫",
            CardStatus.RATE_LIMITED: "⏱️",
            CardStatus.ERROR: "⚠️",
            CardStatus.TIMEOUT: "⏱️",
            CardStatus.UNKNOWN: "❓",
        }.get(self.status, "❓")
    
    def to_display(self) -> str:
        """Format for display to user"""
        confidence_str = f"{int(self.confidence * 100)}%"
        
        if self.status == CardStatus.LIVE:
            return f"✅ LIVE ({confidence_str})"
        elif self.status == CardStatus.CCN:
            return f"🔵 CCN - Number Valid ({confidence_str})"
        elif self.status == CardStatus.CVV_MISMATCH:
            return f"⚠️ CVV Mismatch ({confidence_str})"
        elif self.status == CardStatus.INSUFFICIENT:
            return f"💰 Insufficient Funds ({confidence_str})"
        elif self.status == CardStatus.EXPIRED:
            return f"📅 Expired Card"
        elif self.status == CardStatus.THREE_DS:
            return f"🔐 3D Secure Required"
        elif self.status == CardStatus.RISK:
            return f"🚫 Risk Check Failed"
        elif self.status == CardStatus.RATE_LIMITED:
            return f"⏱️ Rate Limited - Retry Later"
        elif self.status == CardStatus.ERROR:
            return f"⚠️ Gateway Error"
        elif self.status == CardStatus.TIMEOUT:
            return f"⏱️ Timeout"
        else:
            return f"❌ Declined"


# Stripe decline code mappings
STRIPE_DECLINE_CODES = {
    "card_declined": (CardStatus.DECLINED, "Card was declined"),
    "incorrect_cvc": (CardStatus.CVV_MISMATCH, "Incorrect CVC code"),
    "invalid_cvc": (CardStatus.CVV_MISMATCH, "Invalid CVC code"),
    "expired_card": (CardStatus.EXPIRED, "Card has expired"),
    "insufficient_funds": (CardStatus.INSUFFICIENT, "Insufficient funds"),
    "processing_error": (CardStatus.ERROR, "Processing error"),
    "incorrect_number": (CardStatus.INVALID, "Invalid card number"),
    "invalid_number": (CardStatus.INVALID, "Invalid card number"),
    "invalid_expiry_month": (CardStatus.EXPIRED, "Invalid expiry month"),
    "invalid_expiry_year": (CardStatus.EXPIRED, "Invalid expiry year"),
    "fraudulent": (CardStatus.RISK, "Suspected fraud"),
    "lost_card": (CardStatus.RISK, "Card reported lost"),
    "stolen_card": (CardStatus.RISK, "Card reported stolen"),
    "pickup_card": (CardStatus.RISK, "Card should be picked up"),
    "do_not_honor": (CardStatus.DECLINED, "Do not honor"),
    "generic_decline": (CardStatus.DECLINED, "Card declined"),
    "authentication_required": (CardStatus.THREE_DS, "3D Secure required"),
    "card_not_supported": (CardStatus.DECLINED, "Card not supported"),
    "currency_not_supported": (CardStatus.DECLINED, "Currency not supported"),
    "duplicate_transaction": (CardStatus.DECLINED, "Duplicate transaction"),
    "reenter_transaction": (CardStatus.ERROR, "Re-enter transaction"),
    "try_again_later": (CardStatus.ERROR, "Try again later"),
}

# PayPal decline codes
PAYPAL_DECLINE_CODES = {
    "INSTRUMENT_DECLINED": (CardStatus.DECLINED, "Payment declined"),
    "PAYER_ACTION_REQUIRED": (CardStatus.THREE_DS, "Additional verification required"),
    "INTERNAL_SERVICE_ERROR": (CardStatus.ERROR, "PayPal error"),
    "INVALID_SECURITY_CODE_LENGTH": (CardStatus.CVV_MISMATCH, "Invalid CVV length"),
    "CARD_TYPE_NOT_SUPPORTED": (CardStatus.DECLINED, "Card type not supported"),
    "TRANSACTION_REFUSED": (CardStatus.DECLINED, "Transaction refused"),
}

# Braintree decline codes
BRAINTREE_DECLINE_CODES = {
    "2000": (CardStatus.DECLINED, "Do not honor"),
    "2001": (CardStatus.INSUFFICIENT, "Insufficient funds"),
    "2002": (CardStatus.DECLINED, "Limit exceeded"),
    "2003": (CardStatus.RISK, "Cardholder activity limit exceeded"),
    "2004": (CardStatus.EXPIRED, "Expired card"),
    "2005": (CardStatus.CVV_MISMATCH, "Invalid CVV"),
    "2006": (CardStatus.CVV_MISMATCH, "CVV required"),
    "2010": (CardStatus.DECLINED, "Card issuer declined"),
    "2015": (CardStatus.DECLINED, "Transaction not allowed"),
    "2038": (CardStatus.RISK, "Processor declined - fraud"),
    "2046": (CardStatus.DECLINED, "Declined"),
    "2047": (CardStatus.DECLINED, "Call issuer"),
    "2057": (CardStatus.RISK, "Issuer suspected fraud"),
    "3000": (CardStatus.ERROR, "Processor network unavailable"),
}


def parse_stripe_response(response_text: str, status_code: int = 200) -> ParsedResponse:
    """Parse Stripe API response"""
    response_lower = response_text.lower()
    
    # Check for success indicators first
    if any(kw in response_lower for kw in ["succeeded", "requires_capture", "active", "pm_"]):
        if "requires_action" in response_lower or "requires_confirmation" in response_lower:
            return ParsedResponse(
                status=CardStatus.THREE_DS,
                confidence=0.9,
                raw_message=response_text[:200],
                decline_code="authentication_required",
                decline_reason="3D Secure verification required",
                is_retryable=False,
                gateway_name="stripe"
            )
        return ParsedResponse(
            status=CardStatus.LIVE,
            confidence=0.95,
            raw_message=response_text[:200],
            decline_code=None,
            decline_reason=None,
            is_retryable=False,
            gateway_name="stripe"
        )
    
    # Check for specific decline codes
    for code, (status, reason) in STRIPE_DECLINE_CODES.items():
        if code in response_lower:
            confidence = 0.9 if status != CardStatus.DECLINED else 0.85
            return ParsedResponse(
                status=status,
                confidence=confidence,
                raw_message=response_text[:200],
                decline_code=code,
                decline_reason=reason,
                is_retryable=status == CardStatus.ERROR,
                gateway_name="stripe"
            )
    
    # Check for rate limiting
    if status_code == 429 or "rate" in response_lower:
        return ParsedResponse(
            status=CardStatus.RATE_LIMITED,
            confidence=0.95,
            raw_message=response_text[:200],
            decline_code="rate_limited",
            decline_reason="Too many requests",
            is_retryable=True,
            gateway_name="stripe"
        )
    
    # Generic decline
    if "decline" in response_lower or "error" in response_lower:
        return ParsedResponse(
            status=CardStatus.DECLINED,
            confidence=0.7,
            raw_message=response_text[:200],
            decline_code="generic_decline",
            decline_reason="Card declined",
            is_retryable=False,
            gateway_name="stripe"
        )
    
    return ParsedResponse(
        status=CardStatus.UNKNOWN,
        confidence=0.5,
        raw_message=response_text[:200],
        decline_code=None,
        decline_reason=None,
        is_retryable=True,
        gateway_name="stripe"
    )


def parse_paypal_response(response_text: str, status_code: int = 200) -> ParsedResponse:
    """Parse PayPal API response"""
    response_lower = response_text.lower()
    
    # Success indicators
    if any(kw in response_lower for kw in ["completed", "approved", "captured"]):
        return ParsedResponse(
            status=CardStatus.LIVE,
            confidence=0.95,
            raw_message=response_text[:200],
            decline_code=None,
            decline_reason=None,
            is_retryable=False,
            gateway_name="paypal"
        )
    
    # Check for specific decline codes
    for code, (status, reason) in PAYPAL_DECLINE_CODES.items():
        if code.lower() in response_lower:
            return ParsedResponse(
                status=status,
                confidence=0.9,
                raw_message=response_text[:200],
                decline_code=code,
                decline_reason=reason,
                is_retryable=status == CardStatus.ERROR,
                gateway_name="paypal"
            )
    
    # Generic decline
    if "decline" in response_lower or "fail" in response_lower:
        return ParsedResponse(
            status=CardStatus.DECLINED,
            confidence=0.7,
            raw_message=response_text[:200],
            decline_code="generic_decline",
            decline_reason="Payment declined",
            is_retryable=False,
            gateway_name="paypal"
        )
    
    return ParsedResponse(
        status=CardStatus.UNKNOWN,
        confidence=0.5,
        raw_message=response_text[:200],
        decline_code=None,
        decline_reason=None,
        is_retryable=True,
        gateway_name="paypal"
    )


def parse_braintree_response(response_text: str, status_code: int = 200) -> ParsedResponse:
    """Parse Braintree API response"""
    response_lower = response_text.lower()
    
    # Success indicators
    if any(kw in response_lower for kw in ["authorized", "submitted_for_settlement", "settled"]):
        return ParsedResponse(
            status=CardStatus.LIVE,
            confidence=0.95,
            raw_message=response_text[:200],
            decline_code=None,
            decline_reason=None,
            is_retryable=False,
            gateway_name="braintree"
        )
    
    # Check processor response codes
    code_match = re.search(r'"processorResponseCode"\s*:\s*"?(\d+)"?', response_text)
    if code_match:
        code = code_match.group(1)
        if code in BRAINTREE_DECLINE_CODES:
            status, reason = BRAINTREE_DECLINE_CODES[code]
            return ParsedResponse(
                status=status,
                confidence=0.9,
                raw_message=response_text[:200],
                decline_code=code,
                decline_reason=reason,
                is_retryable=status == CardStatus.ERROR,
                gateway_name="braintree"
            )
    
    # CVV check
    if "cvv" in response_lower and any(kw in response_lower for kw in ["fail", "invalid", "mismatch"]):
        return ParsedResponse(
            status=CardStatus.CVV_MISMATCH,
            confidence=0.85,
            raw_message=response_text[:200],
            decline_code="cvv_mismatch",
            decline_reason="CVV verification failed",
            is_retryable=False,
            gateway_name="braintree"
        )
    
    # Generic decline
    if "decline" in response_lower or "error" in response_lower:
        return ParsedResponse(
            status=CardStatus.DECLINED,
            confidence=0.7,
            raw_message=response_text[:200],
            decline_code="generic_decline",
            decline_reason="Card declined",
            is_retryable=False,
            gateway_name="braintree"
        )
    
    return ParsedResponse(
        status=CardStatus.UNKNOWN,
        confidence=0.5,
        raw_message=response_text[:200],
        decline_code=None,
        decline_reason=None,
        is_retryable=True,
        gateway_name="braintree"
    )


def parse_generic_response(response_text: str, gateway_name: str = "unknown") -> ParsedResponse:
    """
    Parse a generic gateway response using keyword matching.
    Use this when a specific parser is not available.
    """
    if not response_text:
        return ParsedResponse(
            status=CardStatus.ERROR,
            confidence=0.5,
            raw_message="Empty response",
            decline_code=None,
            decline_reason="No response from gateway",
            is_retryable=True,
            gateway_name=gateway_name
        )
    
    response_lower = response_text.lower()
    
    # Success patterns (high confidence)
    success_keywords = ["approved", "charged", "success", "captured", "live", "valid"]
    if any(kw in response_lower for kw in success_keywords):
        return ParsedResponse(
            status=CardStatus.LIVE,
            confidence=0.85,
            raw_message=response_text[:200],
            decline_code=None,
            decline_reason=None,
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # CCN patterns
    ccn_patterns = ["ccn", "card number valid", "number valid", "luhn"]
    if any(kw in response_lower for kw in ccn_patterns):
        return ParsedResponse(
            status=CardStatus.CCN,
            confidence=0.8,
            raw_message=response_text[:200],
            decline_code="ccn",
            decline_reason="Card number valid, CVV not verified",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # CVV issues
    cvv_keywords = ["cvv", "cvc", "security code", "incorrect_cvc", "invalid_cvc"]
    if any(kw in response_lower for kw in cvv_keywords):
        return ParsedResponse(
            status=CardStatus.CVV_MISMATCH,
            confidence=0.8,
            raw_message=response_text[:200],
            decline_code="cvv_mismatch",
            decline_reason="CVV verification failed",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Insufficient funds
    if "insufficient" in response_lower or "balance" in response_lower:
        return ParsedResponse(
            status=CardStatus.INSUFFICIENT,
            confidence=0.85,
            raw_message=response_text[:200],
            decline_code="insufficient_funds",
            decline_reason="Insufficient funds",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Expired card
    if "expired" in response_lower or "expiration" in response_lower:
        return ParsedResponse(
            status=CardStatus.EXPIRED,
            confidence=0.9,
            raw_message=response_text[:200],
            decline_code="expired_card",
            decline_reason="Card has expired",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # 3D Secure
    if "3d" in response_lower or "secure" in response_lower or "authentication" in response_lower:
        return ParsedResponse(
            status=CardStatus.THREE_DS,
            confidence=0.75,
            raw_message=response_text[:200],
            decline_code="3ds_required",
            decline_reason="3D Secure verification required",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Fraud/Risk
    fraud_keywords = ["fraud", "risk", "suspicious", "blocked", "restricted"]
    if any(kw in response_lower for kw in fraud_keywords):
        return ParsedResponse(
            status=CardStatus.RISK,
            confidence=0.8,
            raw_message=response_text[:200],
            decline_code="risk_check_failed",
            decline_reason="Risk check failed",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Rate limiting
    if "rate" in response_lower or "limit" in response_lower or "throttle" in response_lower:
        return ParsedResponse(
            status=CardStatus.RATE_LIMITED,
            confidence=0.9,
            raw_message=response_text[:200],
            decline_code="rate_limited",
            decline_reason="Rate limited",
            is_retryable=True,
            gateway_name=gateway_name
        )
    
    # Timeout
    if "timeout" in response_lower or "timed out" in response_lower:
        return ParsedResponse(
            status=CardStatus.TIMEOUT,
            confidence=0.95,
            raw_message=response_text[:200],
            decline_code="timeout",
            decline_reason="Request timed out",
            is_retryable=True,
            gateway_name=gateway_name
        )
    
    # Error patterns
    if "error" in response_lower or "exception" in response_lower:
        return ParsedResponse(
            status=CardStatus.ERROR,
            confidence=0.7,
            raw_message=response_text[:200],
            decline_code="error",
            decline_reason="Gateway error",
            is_retryable=True,
            gateway_name=gateway_name
        )
    
    # Invalid card
    invalid_keywords = ["invalid", "incorrect", "wrong", "bad"]
    if any(kw in response_lower for kw in invalid_keywords):
        return ParsedResponse(
            status=CardStatus.INVALID,
            confidence=0.75,
            raw_message=response_text[:200],
            decline_code="invalid_card",
            decline_reason="Invalid card details",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Generic decline
    if "decline" in response_lower or "denied" in response_lower or "reject" in response_lower:
        return ParsedResponse(
            status=CardStatus.DECLINED,
            confidence=0.7,
            raw_message=response_text[:200],
            decline_code="generic_decline",
            decline_reason="Card declined",
            is_retryable=False,
            gateway_name=gateway_name
        )
    
    # Unknown
    return ParsedResponse(
        status=CardStatus.UNKNOWN,
        confidence=0.4,
        raw_message=response_text[:200],
        decline_code=None,
        decline_reason=None,
        is_retryable=True,
        gateway_name=gateway_name
    )


def auto_parse_response(response_text: str, gateway_name: str, status_code: int = 200) -> ParsedResponse:
    """
    Automatically select and use the appropriate parser based on gateway name.
    """
    gateway_lower = gateway_name.lower()
    
    if "stripe" in gateway_lower:
        return parse_stripe_response(response_text, status_code)
    elif "paypal" in gateway_lower:
        return parse_paypal_response(response_text, status_code)
    elif "braintree" in gateway_lower:
        return parse_braintree_response(response_text, status_code)
    else:
        return parse_generic_response(response_text, gateway_name)
