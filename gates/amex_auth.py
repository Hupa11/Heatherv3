"""
Amex Auth Gateway - American Express Card Validation
Specifically validates Amex cards (15 digits, 4-digit CVV)
Uses the proven Stripe Auth flow with Amex-specific pre-validation
"""

from typing import Tuple
from tools.bin_lookup import get_card_info
from gates.stripe_auth import stripe_auth_check


def is_valid_amex(card_num: str) -> bool:
    """Check if card is a valid Amex format"""
    card_num = card_num.replace(" ", "").replace("-", "")
    
    if not (card_num.startswith("34") or card_num.startswith("37")):
        return False
    if len(card_num) != 15:
        return False
    if not card_num.isdigit():
        return False
    
    total = 0
    reverse_digits = card_num[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n = n * 2
            if n > 9:
                n = n - 9
        total += n
    return total % 10 == 0


def is_valid_amex_cvv(cvv: str) -> bool:
    """Check if CVV is valid Amex format (4 digits)"""
    cvv = cvv.strip()
    return len(cvv) == 4 and cvv.isdigit()


def amex_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, 
                    proxy: str = None) -> Tuple[str, bool]:
    """
    Validate American Express card with Amex-specific pre-validation
    
    Args:
        card_num: 15-digit Amex card number (starting with 34 or 37)
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: 4-digit CID/CVV
        proxy: Optional proxy string
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    card_num = card_num.replace(" ", "").replace("-", "")
    
    if not is_valid_amex(card_num):
        return ("DECLINED ❌ - Not a valid Amex (must be 15 digits starting with 34/37)", True)
    
    if not is_valid_amex_cvv(card_cvc):
        return ("DECLINED ❌ - Amex requires 4-digit CVV/CID", True)
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    bin_info = get_card_info(card_num[:6])
    card_info = ""
    if bin_info:
        brand = bin_info.get('brand', 'AMEX')
        bank = bin_info.get('bank', 'Unknown')
        level = bin_info.get('level', '')
        flag = bin_info.get('flag', '🇺🇸')
        card_info = f" | {flag} {brand} | {bank}"
        if level:
            card_info += f" | {level}"
    else:
        card_info = " | 🇺🇸 AMERICAN EXPRESS"
    
    result, proxy_ok = stripe_auth_check(card_num, card_mon, card_yer, card_cvc, proxy=proxy)
    
    result_lower = result.lower() if result else ""
    
    if "approved" in result_lower or "success" in result_lower or "live" in result_lower:
        return (f"APPROVED ✅ - Amex Valid{card_info}", proxy_ok)
    elif "ccn" in result_lower:
        return (f"CCN ✅ - Card valid, CVV issue{card_info}", proxy_ok)
    elif "insufficient" in result_lower:
        return (f"APPROVED ✅ - Live (insufficient funds){card_info}", proxy_ok)
    elif "3d" in result_lower or "secure" in result_lower:
        return (f"3D SECURE 🔒 - Requires auth{card_info}", proxy_ok)
    elif "expired" in result_lower:
        return (f"DECLINED ❌ - Expired{card_info}", proxy_ok)
    else:
        return (f"DECLINED ❌ - {result}{card_info}", proxy_ok)


async def amex_auth_check_async(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                                 proxy: str = None) -> Tuple[str, bool]:
    """Async wrapper for amex_auth_check"""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, amex_auth_check, card_num, card_mon, card_yer, card_cvc, proxy)
