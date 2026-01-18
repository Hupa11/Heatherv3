"""
VBV (Verified by Visa) / 3DS Lookup API Integration
Uses voidapi.xyz for BIN and VBV status lookup
"""

import os
import requests
from typing import Tuple, Dict, Optional


VBV_API_KEY = os.environ.get("VBV_API_KEY", "")
VBV_API_URL = "https://api.voidapi.xyz/v2/vbv"


def lookup_vbv(card_number: str, timeout: int = 15) -> Tuple[bool, Dict]:
    """
    Lookup VBV/3DS status for a card.
    
    Args:
        card_number: Full card number or just BIN (first 6-8 digits)
        timeout: Request timeout
    
    Returns:
        Tuple of (success, data_dict)
        data_dict contains: bin, scheme, type, level, bank, country, emoji, status
    """
    if not VBV_API_KEY:
        return False, {"error": "VBV_API_KEY not configured"}
    
    try:
        card_clean = card_number.replace(" ", "").replace("-", "")
        
        params = {
            "key": VBV_API_KEY,
            "card": card_clean
        }
        
        response = requests.get(VBV_API_URL, params=params, timeout=timeout)
        
        if response.status_code != 200:
            return False, {"error": f"API returned {response.status_code}"}
        
        data = response.json()
        
        if data.get("success"):
            return True, data.get("data", {})
        else:
            return False, {"error": data.get("message", "Unknown error")}
    
    except requests.exceptions.Timeout:
        return False, {"error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return False, {"error": f"Network error: {str(e)[:50]}"}
    except Exception as e:
        return False, {"error": str(e)[:50]}


def format_vbv_response(card_input: str, data: Dict) -> str:
    """Format VBV lookup result for display"""
    
    bin_num = data.get("bin", "Unknown")
    scheme = data.get("scheme", "Unknown")
    card_type = data.get("type", "Unknown")
    level = data.get("level", "Unknown")
    bank = data.get("bank", "Unknown")
    country = data.get("country", "Unknown")
    emoji = data.get("emoji", "")
    status = data.get("status", "Unknown")
    
    status_emoji = "✅" if "success" in status.lower() or "frictionless" in status.lower() else "⚠️"
    if "failed" in status.lower() or "error" in status.lower():
        status_emoji = "❌"
    
    vbv_interpretation = interpret_vbv_status(status)
    
    response = f"""<b>━━━━━ VBV/3DS LOOKUP ━━━━━</b>

<b>Card:</b> <code>{card_input[:6]}xxxxxx</code>
<b>BIN:</b> <code>{bin_num}</code>

<b>Scheme:</b> {scheme}
<b>Type:</b> {card_type}
<b>Level:</b> {level}
<b>Bank:</b> {bank}
<b>Country:</b> {country} {emoji}

<b>VBV Status:</b> {status_emoji} <code>{status}</code>
<b>Meaning:</b> {vbv_interpretation}

<b>━━━━━━━━━━━━━━━━━━━━</b>"""
    
    return response


def interpret_vbv_status(status: str) -> str:
    """Interpret VBV status into human-readable meaning"""
    status_lower = status.lower()
    
    if "authenticate_successful" in status_lower:
        return "Card supports 3DS - Full authentication required"
    elif "authenticate_frictionless" in status_lower:
        if "failed" in status_lower:
            return "3DS frictionless failed - May bypass 3DS"
        return "3DS frictionless - Low friction authentication"
    elif "not_enrolled" in status_lower:
        return "Card NOT enrolled in 3DS - No VBV required"
    elif "authentication_unavailable" in status_lower:
        return "3DS unavailable - May skip verification"
    elif "authentication_attempted" in status_lower:
        return "3DS attempted but not completed"
    elif "challenge" in status_lower:
        return "3DS challenge required - Full verification needed"
    else:
        return "Unknown VBV status"


if __name__ == "__main__":
    success, data = lookup_vbv("4147768578745265")
    if success:
        print(format_vbv_response("4147768578745265|04|2026|168", data))
    else:
        print(f"Error: {data}")
