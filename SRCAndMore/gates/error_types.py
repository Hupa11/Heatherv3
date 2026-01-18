"""
Gateway Error Type Definitions
Standardized error types for consistent error handling and logging across all gateways
"""

from enum import Enum


class GatewayErrorType(Enum):
    """Enumeration of all possible gateway error types"""
    
    # Network-related errors
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PROXY_ERROR = "proxy_error"
    DNS_ERROR = "dns_error"
    NETWORK_ERROR = "network_error"
    
    # Rate limiting and throttling
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TOO_MANY_REQUESTS = "too_many_requests"
    
    # Authentication/Authorization errors
    AUTH_ERROR = "auth_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INVALID_CREDENTIALS = "invalid_credentials"
    
    # Card validation errors
    INVALID_CARD = "invalid_card"
    INVALID_NUMBER = "invalid_number"
    INVALID_EXPIRY = "invalid_expiry"
    INVALID_CVV = "invalid_cvv"
    
    # Card status errors
    EXPIRED_CARD = "expired_card"
    RESTRICTED_CARD = "restricted_card"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    CVV_MISMATCH = "cvv_mismatch"
    
    # Fraud/Security errors
    FRAUD_CHECK = "fraud_check"
    RISK_DISALLOWED = "risk_disallowed"
    ISSUER_DECLINE = "issuer_decline"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    
    # Gateway configuration errors
    INVALID_RESPONSE = "invalid_response"
    MISSING_CONFIGURATION = "missing_configuration"
    INVALID_GATEWAY_CONFIG = "invalid_gateway_config"
    API_ERROR = "api_error"
    
    # Card decline reasons
    GENERIC_DECLINE = "generic_decline"
    UNKNOWN_DECLINE = "unknown_decline"
    
    # Other errors
    UNKNOWN = "unknown"
    INTERNAL_ERROR = "internal_error"


def error_type_from_response(response_text: str, status_code: int = None) -> GatewayErrorType:
    """
    Map a response text or status code to a GatewayErrorType
    
    Args:
        response_text: Response body from gateway
        status_code: HTTP status code (optional)
    
    Returns:
        GatewayErrorType matching the error pattern
    """
    if response_text is None:
        response_text = ""
    
    response_lower = response_text.lower()
    
    # HTTP status code based classification
    if status_code:
        if status_code == 429:
            return GatewayErrorType.RATE_LIMITED
        elif status_code == 503:
            return GatewayErrorType.SERVICE_UNAVAILABLE
        elif status_code == 401:
            return GatewayErrorType.AUTH_ERROR
        elif status_code == 403:
            return GatewayErrorType.FORBIDDEN
        elif status_code >= 500:
            return GatewayErrorType.API_ERROR
    
    # Response text pattern matching
    rate_limit_keywords = ['rate', 'limit', 'throttle', 'quota', 'exceeded']
    if any(kw in response_lower for kw in rate_limit_keywords):
        return GatewayErrorType.RATE_LIMITED
    
    timeout_keywords = ['timeout', 'timed out', 'deadline', 'exceeded']
    if any(kw in response_lower for kw in timeout_keywords):
        return GatewayErrorType.TIMEOUT
    
    proxy_keywords = ['proxy', 'socks', 'connection', 'gateway']
    if any(kw in response_lower for kw in proxy_keywords):
        return GatewayErrorType.PROXY_ERROR
    
    auth_keywords = ['auth', 'invalid.*credential', 'token', 'unauthorized', 'forbidden']
    if any(kw in response_lower for kw in auth_keywords):
        return GatewayErrorType.AUTH_ERROR
    
    card_keywords = ['invalid.*card', 'bad.*card', 'invalid.*number']
    if any(kw in response_lower for kw in card_keywords):
        return GatewayErrorType.INVALID_CARD
    
    cvv_keywords = ['cvv', 'cvc', 'security', 'code', 'invalid_security_code']
    if any(kw in response_lower for kw in cvv_keywords):
        return GatewayErrorType.CVV_MISMATCH
    
    expired_keywords = ['expired', 'expiration', 'expired_card']
    if any(kw in response_lower for kw in expired_keywords):
        return GatewayErrorType.EXPIRED_CARD
    
    insufficient_keywords = ['insufficient', 'funds', 'balance', 'limit']
    if any(kw in response_lower for kw in insufficient_keywords):
        return GatewayErrorType.INSUFFICIENT_FUNDS
    
    fraud_keywords = ['fraud', 'risk', 'disallowed', 'suspicious', 'issuer.*decline', 'decline']
    if any(kw in response_lower for kw in fraud_keywords):
        return GatewayErrorType.FRAUD_CHECK
    
    # Default to unknown
    return GatewayErrorType.UNKNOWN


def get_error_message(error_type: GatewayErrorType) -> str:
    """
    Get a user-friendly message for an error type
    
    Args:
        error_type: The error type enum value
    
    Returns:
        A readable error message
    """
    messages = {
        GatewayErrorType.TIMEOUT: "Request timed out",
        GatewayErrorType.CONNECTION_ERROR: "Connection failed",
        GatewayErrorType.PROXY_ERROR: "Proxy connection failed",
        GatewayErrorType.RATE_LIMITED: "Rate limited by provider",
        GatewayErrorType.SERVICE_UNAVAILABLE: "Service temporarily unavailable",
        GatewayErrorType.AUTH_ERROR: "Authentication failed",
        GatewayErrorType.INVALID_CARD: "Invalid card number",
        GatewayErrorType.EXPIRED_CARD: "Card has expired",
        GatewayErrorType.INSUFFICIENT_FUNDS: "Insufficient funds",
        GatewayErrorType.CVV_MISMATCH: "CVV verification failed",
        GatewayErrorType.FRAUD_CHECK: "Fraudulent activity detected",
        GatewayErrorType.INVALID_RESPONSE: "Invalid response from gateway",
        GatewayErrorType.GENERIC_DECLINE: "Card declined",
        GatewayErrorType.UNKNOWN: "Unknown error occurred",
    }
    return messages.get(error_type, "An error occurred")
