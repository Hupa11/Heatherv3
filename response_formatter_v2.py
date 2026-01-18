"""
Enhanced Response Formatter with Purple Border Layout
Formats card check responses with detailed BIN info, security type, and VBV status.
"""
from enum import Enum
from typing import Tuple, Dict, Optional
from dataclasses import dataclass
import json
from datetime import datetime
from response_formatter import ApprovalStatus, ErrorType, GatewayResponse

# ============================================================================
# Enhanced Formatters with New Layout
# ============================================================================

def get_card_type(card_number: str) -> str:
    """Detect card type from BIN."""
    if not card_number or len(card_number) < 1:
        return "UNKNOWN"
    
    first_digit = card_number[0]
    if first_digit == '4':
        return "VISA"
    elif first_digit == '5':
        return "MASTERCARD"
    elif first_digit == '3':
        return "AMEX"
    elif first_digit == '6':
        return "DISCOVER"
    else:
        return "UNKNOWN"

def format_card_response_v2(
    gateway_name: str,
    card_input: str,
    status: ApprovalStatus,
    message: str = "No response",
    elapsed_sec: float = 0.0,
    security_type: str = "Unknown",
    vbv_status: str = "Failed",
    proxy_alive: bool = True,
    bank_name: str = "Unknown",
    country: str = "Unknown",
    amount_usd: float = 0.01
) -> str:
    """
    Format card response with clean, professional stacked layout.
    Shows essential card information without API noise.
    
    Args:
        gateway_name: Name of the gateway tested
        card_input: Card in format CARD|MM|YY|CVV
        status: ApprovalStatus enum
        message: Response message from gateway
        elapsed_sec: Time taken for check
        security_type: 2D/3D/etc
        vbv_status: VBV/AVV status
        proxy_alive: Whether proxy worked
        bank_name: Bank issuing the card
        country: Country of card
        amount_usd: Amount charged/tested (in USD)
    """
    # Extract card parts
    card_parts = card_input.split('|')
    card_number = card_parts[0] if card_parts else "0000000000000000"
    bin_num = card_number[:6]
    card_type = get_card_type(card_number)
    
    # Status badges and CVV/CCN info
    status_display = {
        ApprovalStatus.APPROVED: ("✅ APPROVED", "✅ Match", "✅ Live"),
        ApprovalStatus.CVV_ISSUE: ("❌ CVV MISMATCH", "❌ Mismatch", "✅ Live"),
        ApprovalStatus.INSUFFICIENT_FUNDS: ("✅ CCN", "✅ Match", "✅ Live (No Funds)"),
        ApprovalStatus.DECLINED: ("❌ DECLINED", "❌ N/A", "❌ Dead"),
        ApprovalStatus.FRAUD_CHECK: ("❌ 3DS REQUIRED", "❌ N/A", "⚠️ 3DS Block"),
        ApprovalStatus.EXPIRED: ("❌ EXPIRED", "❌ N/A", "❌ Dead"),
        ApprovalStatus.ERROR: ("❌ ERROR", "❌ N/A", "❌ Unknown"),
        ApprovalStatus.UNKNOWN: ("❌ UNKNOWN", "❌ N/A", "❌ Unknown"),
    }
    
    status_info = status_display.get(status, ("❌ UNKNOWN", "❌ N/A", "❌ Unknown"))
    status_text, cvv_status, ccn_status = status_info
    proxy_status = "🟢 Alive" if proxy_alive else "🔴 Dead"
    
    # Format amount
    amount_str = f"${amount_usd:.2f} USD" if amount_usd > 0 else "Free"
    
    response = f"""<b>{status_text}</b>

<code>{card_input}</code>
<b>Card Type:</b> {card_type}

<b>CVV:</b> {cvv_status}
<b>CCN:</b> {ccn_status}

<b>BIN:</b> {bin_num}
<b>Bank:</b> {bank_name}
<b>Country:</b> {country}

<b>Gateway:</b> {gateway_name}
<b>Amount:</b> {amount_str}

<b>Time:</b> {elapsed_sec:.2f}s
<b>Proxy:</b> {proxy_status}"""
    
    return response

def format_approved_response_v2(
    gateway_name: str,
    card_input: str,
    elapsed_sec: float = 0.0,
    amount_charged: str = "$0.01 USD",
    security_type: str = "2D",
    vbv_status: str = "Successful",
    proxy_alive: bool = True,
    progress: Optional[str] = None
) -> str:
    """
    Format approved card response with clean stacked layout.
    Used to display successful card hits in mass checks.
    """
    card_parts = card_input.split('|')
    card_number = card_parts[0] if card_parts else "0000000000000000"
    bin_num = card_number[:6]
    card_type = get_card_type(card_number)
    proxy_status = "🟢 Alive" if proxy_alive else "🔴 Dead"
    
    response = f"""✅ <b>APPROVED</b>

<code>{card_input}</code>
<b>Card Type:</b> {card_type}

<b>CVV:</b> ✅ Match
<b>CCN:</b> ✅ Live

<b>BIN:</b> {bin_num}
<b>Amount Charged:</b> {amount_charged}

<b>Gateway:</b> {gateway_name}
<b>VBV:</b> {vbv_status}

<b>Time:</b> {elapsed_sec:.2f}s
<b>Proxy:</b> {proxy_status}"""
    
    if progress:
        response += f"\n<b>Progress:</b> {progress}"
    
    return response

def format_mass_check_start(
    gateway_name: str,
    filename: str,
    total_cards: int,
    proxy_status: bool = True
) -> str:
    """Format the start of mass check with progress header."""
    proxy_emoji = "🟢" if proxy_status else "🔴"
    
    header = f"""<b>🚀 Starting Mass Check</b>

<b>Gateway:</b> {gateway_name}
<b>File:</b> {filename}
<b>Total Cards:</b> {total_cards}
{proxy_emoji} <b>Proxy:</b> {'Alive' if proxy_status else 'Dead'}

<b>Progress:</b> 0/{total_cards}
"""
    return header

def format_mass_check_progress(current: int, total: int) -> str:
    """Format progress update for mass checks (every 10 cards)."""
    percent = (current / total * 100) if total > 0 else 0
    bar_length = 20
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_length - filled)
    
    return f"<b>Progress:</b> [{bar}] {current}/{total} ({percent:.1f}%)"

def format_mass_summary_v2(
    gateway_name: str,
    total: int,
    approved: int,
    cvv_mismatch: int = 0,
    insufficient_funds: int = 0,
    failed: int = 0,
    elapsed_sec: float = 0.0,
    proxy_alive: bool = True
) -> str:
    """Format comprehensive mass check summary."""
    success_rate = (approved / total * 100) if total > 0 else 0
    avg_per_card = elapsed_sec / total if total > 0 else 0
    proxy_status = "🟢 Alive" if proxy_alive else "🔴 Dead"
    
    summary = f"""✅ MASS CHECK COMPLETE

Gateway: {gateway_name}
Total Cards: {total}

Results:
Approved: {approved}
CVV Mismatch: {cvv_mismatch}
Insufficient: {insufficient_funds}
Failed: {failed}

Success Rate: {success_rate:.1f}%
Total Time: {elapsed_sec:.2f}s ({avg_per_card:.2f}s/card)
Proxy: {proxy_status}"""
    
    return summary


def format_batch_dashboard(
    gateway_name: str,
    current: int,
    total: int,
    approved: int = 0,
    cvv: int = 0,
    three_ds: int = 0,
    low_funds: int = 0,
    declined: int = 0,
    last_card: str = "",
    last_status: str = "",
    is_paused: bool = False
) -> str:
    """
    Format compact batch check dashboard with inline stats.
    Professional 8-line layout for real-time updates.
    """
    percent = (current / total * 100) if total > 0 else 0
    bar_len = 15
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "▓" * filled + "░" * (bar_len - filled)
    
    status_icon = "⏸" if is_paused else "⚡"
    status_text = "PAUSED" if is_paused else "RUNNING"
    
    last_card_display = last_card[:6] + "..." + last_card[-4:] if len(last_card) > 10 else last_card
    
    dashboard = f"""<b>{status_icon} {gateway_name}</b>
[{bar}] {current}/{total} ({percent:.0f}%)

✓<b>{approved}</b> | ✗<b>{declined}</b> | CVV<b>{cvv}</b> | 3DS<b>{three_ds}</b> | NSF<b>{low_funds}</b>

<code>{last_card_display}</code>
<i>{last_status[:50]}</i>"""
    
    return dashboard


def format_card_result_compact(
    card_input: str,
    status: str,
    card_type: str = "VISA",
    bank_name: str = "Unknown",
    country: str = "US",
    country_flag: str = "🇺🇸",
    elapsed_sec: float = 0.0,
    amount: str = "$0.50"
) -> str:
    """
    Format compact card result (6 lines max).
    Used for individual hit notifications during batch checks.
    """
    card_parts = card_input.split('|')
    card_number = card_parts[0] if card_parts else "0000000000000000"
    
    masked_card = card_number[:6] + "•" * 6 + card_number[-4:] if len(card_number) >= 16 else card_number
    
    status_emoji = "✅" if "success" in status.lower() or "donation" in status.lower() else ("💰" if "insufficient" in status.lower() else "❌")
    
    response = f"""{status_emoji} <b>{status[:30]}</b>
<code>{card_input}</code>
{card_type} • {country} {country_flag} • {bank_name[:20]}
⏱ {elapsed_sec:.1f}s • {amount}"""
    
    return response


def format_batch_summary_compact(
    gateway_name: str,
    total: int,
    approved: int,
    cvv: int = 0,
    three_ds: int = 0,
    low_funds: int = 0,
    declined: int = 0,
    elapsed_sec: float = 0.0,
    was_stopped: bool = False
) -> str:
    """Format compact batch check summary."""
    status = "⏹ STOPPED" if was_stopped else "✅ COMPLETE"
    rate = (approved / total * 100) if total > 0 else 0
    avg = elapsed_sec / total if total > 0 else 0
    
    summary = f"""<b>{status}</b> • {gateway_name}

📊 <b>Results</b>
✓ <b>{approved}</b> Hits | ✗ <b>{declined}</b> Dead
CVV <b>{cvv}</b> | 3DS <b>{three_ds}</b> | NSF <b>{low_funds}</b>

⏱ {elapsed_sec:.1f}s ({avg:.1f}s/card) • {rate:.1f}% hit rate"""
    
    return summary

if __name__ == "__main__":
    print("Testing Enhanced Response Formatters")
    print("=" * 50)
    
    # Test single card response
    response = format_card_response_v2(
        gateway_name="Stripe Auth",
        card_input="4111111111111111|12|25|123",
        status=ApprovalStatus.APPROVED,
        message="Authorization successful",
        elapsed_sec=2.34,
        security_type="2D",
        vbv_status="Successful",
        proxy_alive=True,
        bank_name="CHASE BANK",
        country="USA"
    )
    print(response)
    print("\n" + "=" * 50 + "\n")
    
    # Test approved response
    approved = format_approved_response_v2(
        gateway_name="Stripe Auth",
        card_input="4111111111111111|12|25|123",
        elapsed_sec=2.34,
        amount_charged="$0.01 USD",
        security_type="2D",
        vbv_status="Successful",
        progress="1/100"
    )
    print(approved)
    print("\n" + "=" * 50 + "\n")
    
    # Test mass check start
    start = format_mass_check_start(
        gateway_name="Stripe Auth",
        filename="cards.txt",
        total_cards=100,
        proxy_status=True
    )
    print(start)
    print("\n" + "=" * 50 + "\n")
    
    # Test progress
    progress = format_mass_check_progress(50, 100)
    print(progress)
    print("\n" + "=" * 50 + "\n")
    
    # Test summary
    summary = format_mass_summary_v2(
        gateway_name="Stripe Auth",
        total=100,
        approved=25,
        cvv_mismatch=5,
        insufficient_funds=3,
        failed=67,
        elapsed_sec=234.56
    )
    print(summary)
