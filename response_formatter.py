"""
Unified Response Formatter for Phase 6 Bot.
Standardizes gateway check results into consistent response objects and formatted strings.
"""
from enum import Enum
from typing import Tuple, Dict, Optional
from dataclasses import dataclass
import json
from datetime import datetime

# ============================================================================
# Status Enums - Normalized across all gateways
# ============================================================================

class ApprovalStatus(Enum):
    """Standardized status for card checks."""
    APPROVED = "approved"           # Card authorized successfully
    DECLINED = "declined"           # Card explicitly rejected
    CVV_ISSUE = "cvv_issue"        # CVV/CVC validation failed
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Declined due to balance
    EXPIRED = "expired"             # Card expired
    INVALID_ACCOUNT = "invalid_account"  # Account issue
    FRAUD_CHECK = "fraud_check"    # 3DS/risk check required
    ERROR = "error"                 # Technical error
    UNKNOWN = "unknown"             # Unknown result

class ErrorType(Enum):
    """Standardized error types."""
    TIMEOUT = "timeout"
    PROXY_ERROR = "proxy_error"
    API_ERROR = "api_error"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN_ERROR = "unknown_error"

# ============================================================================
# Response Data Class
# ============================================================================

@dataclass
class GatewayResponse:
    """Standardized gateway response object."""
    gateway_name: str
    status: ApprovalStatus
    message: str
    raw_response: Optional[str] = None
    elapsed_ms: Optional[int] = None
    error_type: Optional[ErrorType] = None
    error_detail: Optional[str] = None
    proxy_ok: bool = True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            'gateway': self.gateway_name,
            'status': self.status.value,
            'message': self.message,
            'elapsed_ms': self.elapsed_ms,
            'error': self.error_type.value if self.error_type else None,
            'error_detail': self.error_detail,
            'proxy_ok': self.proxy_ok,
            'timestamp': datetime.now().isoformat()
        }

# ============================================================================
# Result Mapping for Common Gateways
# ============================================================================

GATEWAY_RESPONSE_MAPPINGS = {
    'stripe_auth': {
        'keywords': {
            'approved': ['approved', 'succeeded', 'success', 'charged', 'completed'],
            'declined': ['declined', 'rejected', 'failed', 'error', 'invalid'],
            'cvv_issue': ['cvc', 'cvv', 'security_code'],
            'insufficient_funds': ['insufficient', 'insufficient_funds', 'card_declined'],
            'expired': ['expired', 'past_due'],
            'fraud_check': ['3d_secure', '3ds', 'authenticate', 'challenge'],
        }
    },
    'paypal': {
        'keywords': {
            'approved': ['accesstoken', 'cartid', 'approved', 'success'],
            'declined': ['declined', 'reject', 'error', 'invalid'],
            'cvv_issue': ['invalid_security_code', 'cvv'],
            'insufficient_funds': ['insufficient_funds', 'card_limited'],
            'fraud_check': ['authentication', 'challenge'],
        }
    },
    'charge_gates': {
        'keywords': {
            'approved': ['success', 'approved', 'charged', 'payment_intent'],
            'declined': ['declined', 'failed', 'error'],
            'cvv_issue': ['cvc', 'security'],
            'fraud_check': ['3d', 'authentication'],
        }
    }
}

# ============================================================================
# Formatter Functions
# ============================================================================

def map_response_status(gateway_name: str, result_text: str, 
                       is_error: bool = False) -> ApprovalStatus:
    """
    Map raw gateway response to standardized status.
    
    Args:
        gateway_name: Name of the gateway (e.g., 'stripe_auth', 'paypal')
        result_text: Raw response text from gateway
        is_error: Whether an error occurred
    
    Returns:
        ApprovalStatus enum value
    """
    if not result_text:
        return ApprovalStatus.UNKNOWN
    
    result_lower = result_text.lower()
    
    # Determine gateway group
    if 'paypal' in gateway_name.lower():
        mapping = GATEWAY_RESPONSE_MAPPINGS['paypal']
    elif 'charge' in gateway_name.lower():
        mapping = GATEWAY_RESPONSE_MAPPINGS['charge_gates']
    else:
        mapping = GATEWAY_RESPONSE_MAPPINGS['stripe_auth']
    
    # Check keywords in order of specificity
    for status, keywords in mapping['keywords'].items():
        if any(keyword in result_lower for keyword in keywords):
            return ApprovalStatus[status.upper()]
    
    # If no keyword match, try generic patterns
    if is_error or 'error' in result_lower:
        return ApprovalStatus.ERROR
    elif any(word in result_lower for word in ['approved', 'success', 'charged', 'created']):
        return ApprovalStatus.APPROVED
    elif any(word in result_lower for word in ['declined', 'failed', 'rejected']):
        return ApprovalStatus.DECLINED
    
    return ApprovalStatus.UNKNOWN

def format_single_card_response(gateway_name: str, card_input: str, 
                               status: ApprovalStatus, message: str,
                               proxy_status: str = "⚪ Proxy: Unknown") -> str:
    """
    Format single card check response for Telegram.
    
    Args:
        gateway_name: Gateway name (e.g., "Stripe Auth")
        card_input: Card string (CARD|MM|YY|CVV)
        status: ApprovalStatus enum
        message: Raw response message from gateway
        proxy_status: Proxy status emoji string
    
    Returns:
        Formatted HTML string for Telegram
    """
    status_emoji = {
        ApprovalStatus.APPROVED: "✅",
        ApprovalStatus.DECLINED: "❌",
        ApprovalStatus.CVV_ISSUE: "⚠️",
        ApprovalStatus.INSUFFICIENT_FUNDS: "💸",
        ApprovalStatus.EXPIRED: "📅",
        ApprovalStatus.FRAUD_CHECK: "🔐",
        ApprovalStatus.ERROR: "⚡",
        ApprovalStatus.UNKNOWN: "❓",
    }
    
    emoji = status_emoji.get(status, "❓")
    
    response = f"""
━━━━━━━━━━━━━━━━━━
{emoji} <b>Gateway:</b> {gateway_name}
💳 <b>Card:</b> <code>{card_input}</code>
📊 <b>Status:</b> {status.value.upper()}
📝 <b>Response:</b> {message}
{proxy_status}
━━━━━━━━━━━━━━━━━━
    """.strip()
    
    return response

def format_approved_card_response(card_input: str, gateway_name: str, 
                                 amount: str = "Unknown", 
                                 card_type: str = "Unknown",
                                 progress: Optional[str] = None) -> str:
    """
    Format approved card notification for mass checks.
    
    Args:
        card_input: Card string (CARD|MM|YY|CVV)
        gateway_name: Gateway name
        amount: Charged amount (e.g., "$0.01 USD")
        card_type: Card brand (Visa, Mastercard, etc.)
        progress: Progress string (e.g., "1/50")
    
    Returns:
        Formatted HTML string for Telegram
    """
    card_parts = card_input.split('|')
    bin_num = card_parts[0][:6] if card_parts else "000000"
    
    msg = f"""
✅ <b>APPROVED CARD</b> ✅

💳 <b>Card:</b> <code>{card_input}</code>
🏪 <b>Gateway:</b> {gateway_name}
💵 <b>Amount:</b> {amount}
🔐 <b>Card Type:</b> {card_type}

💰 <b>BIN Info:</b>
• BIN: {bin_num}
• Brand: {card_type}
• Country: UNKNOWN
• Bank: UNKNOWN
    """.strip()
    
    if progress:
        msg += f"\n📈 <b>Progress:</b> {progress}"
    
    return msg

def format_mass_summary(gateway_name: str, total: int, approved: int, 
                       failed: int, elapsed_sec: Optional[float] = None) -> str:
    """
    Format mass check summary.
    
    Args:
        gateway_name: Gateway name
        total: Total cards checked
        approved: Number approved
        failed: Number failed
        elapsed_sec: Elapsed time in seconds
    
    Returns:
        Formatted HTML string for Telegram
    """
    success_rate = (approved / total * 100) if total > 0 else 0
    
    msg = f"""
✅ <b>{gateway_name} Mass Check Complete</b>

📊 <b>Summary:</b>
• Total: {total}
• ✅ Approved: {approved} ({success_rate:.1f}%)
• ❌ Failed: {failed}
    """.strip()
    
    if elapsed_sec:
        avg_per_card = elapsed_sec / total if total > 0 else 0
        msg += f"\n⏱️ <b>Time:</b> {elapsed_sec:.1f}s ({avg_per_card:.1f}s/card)"
    
    return msg

def parse_gateway_response(gateway_name: str, response_text: str, 
                          proxy_ok: bool = True) -> GatewayResponse:
    """
    Parse gateway response and create standardized GatewayResponse object.
    
    Args:
        gateway_name: Gateway name
        response_text: Raw response from gateway
        proxy_ok: Whether proxy was working
    
    Returns:
        GatewayResponse object with mapped status
    """
    is_error = "Error:" in response_text or "error" in response_text.lower()
    status = map_response_status(gateway_name, response_text, is_error)
    
    return GatewayResponse(
        gateway_name=gateway_name,
        status=status,
        message=response_text,
        proxy_ok=proxy_ok,
        raw_response=response_text[:200] if response_text else None
    )

# ============================================================================
# Logging Helpers
# ============================================================================

def log_check_result(response: GatewayResponse, card_bin: str = "UNKNOWN",
                    user_id: Optional[int] = None) -> None:
    """
    Log standardized check result for metrics.
    
    Args:
        response: GatewayResponse object
        card_bin: BIN of card checked
        user_id: Telegram user ID
    """
    log_entry = response.to_dict()
    log_entry['card_bin'] = card_bin
    log_entry['user_id'] = user_id
    
    # Write to metrics file
    try:
        with open('logs/metrics.json', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"[!] Error writing metrics: {e}")

if __name__ == '__main__':
    # Test response formatter
    print("Testing Response Formatter")
    print("=" * 50)
    
    # Test status mapping
    test_responses = [
        ('stripe_auth', 'SUCCEEDED'),
        ('paypal', 'accessToken found'),
        ('charge1', 'declined'),
        ('woostripe', 'Error: Timeout'),
    ]
    
    for gateway, response in test_responses:
        status = map_response_status(gateway, response)
        print(f"{gateway}: {response[:30]:30} -> {status.value}")
    
    print("=" * 50)
    
    # Test formatted output
    single = format_single_card_response(
        "Stripe Auth",
        "4111111111111111|12|25|123",
        ApprovalStatus.APPROVED,
        "Authorization successful"
    )
    print(single)
