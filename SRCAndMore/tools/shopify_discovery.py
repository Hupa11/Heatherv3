"""
Shopify Product Discovery - Scans stores and caches products
"""

import asyncio
import httpx
import random
from urllib.parse import urlparse

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
]

def capture(data, first, last):
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

async def discover_store_products(store_url: str, proxy: str = None) -> dict:
    """
    Discover products from a Shopify store
    Returns dict with products, storefront_token, currency, country
    """
    ua = random.choice(USER_AGENTS)
    
    parsed = urlparse(store_url if store_url.startswith("http") else f"https://{store_url}")
    domain = parsed.netloc or store_url
    base_url = f"https://{domain}"
    
    proxy_url = None
    if proxy:
        try:
            parts = proxy.split(':')
            if len(parts) == 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            else:
                proxy_url = f"http://{parts[0]}:{parts[1]}"
        except:
            pass
    
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=30, follow_redirects=True, verify=False) as session:
            headers = {"User-Agent": ua}
            
            resp = await session.get(f"{base_url}/products.json", headers=headers)
            if resp.status_code != 200:
                return {"error": f"Site unreachable (status {resp.status_code})"}
            
            products_data = resp.json().get("products", [])
            products = []
            
            for product in products_data:
                variants = product.get("variants", [])
                title = product.get("title", "Unknown")
                
                for variant in variants:
                    variant_id = variant.get("id")
                    available = variant.get("available", False)
                    price = float(variant.get("price", 0))
                    
                    if price >= 0.1 and available and variant_id:
                        products.append({
                            "variant_id": variant_id,
                            "title": f"{title} - {variant.get('title', '')}".strip(" -"),
                            "price": price,
                            "available": available,
                        })
            
            resp = await session.get(base_url, headers=headers)
            storefront_token = capture(resp.text, '"accessToken":"', '"')
            currency = capture(resp.text, '"currencyCode":"', '"') or "USD"
            country = capture(resp.text, '"countryCode":"', '"') or "US"
            
            return {
                "products": products,
                "storefront_token": storefront_token,
                "currency": currency,
                "country": country,
                "domain": domain,
            }
            
    except httpx.TimeoutException:
        return {"error": "Request timeout"}
    except Exception as e:
        return {"error": str(e)[:100]}

async def scan_store(store_id: int, store_url: str, proxy: str = None):
    """Scan a store and update the database"""
    from tools.shopify_db import update_store_products, mark_store_error
    
    result = await discover_store_products(store_url, proxy)
    
    if "error" in result:
        mark_store_error(store_id, result["error"])
        return False, result["error"]
    
    products = result.get("products", [])
    if not products:
        mark_store_error(store_id, "No available products found")
        return False, "No products"
    
    update_store_products(
        store_id,
        products,
        storefront_token=result.get("storefront_token"),
        currency=result.get("currency"),
        country=result.get("country"),
    )
    
    return True, f"Found {len(products)} products"

async def scan_pending_stores(proxy: str = None, limit: int = 5):
    """Scan all pending stores"""
    from tools.shopify_db import get_stores_to_scan
    
    stores = get_stores_to_scan(limit)
    results = []
    
    for store in stores:
        success, message = await scan_store(store["id"], store["url"], proxy)
        results.append({
            "domain": store["domain"],
            "success": success,
            "message": message,
        })
        await asyncio.sleep(1)
    
    return results

async def scan_all_pending_stores(proxy: str = None, concurrency: int = 10, progress_callback=None):
    """
    Scan ALL pending stores with high concurrency for speed
    
    Args:
        proxy: Proxy string
        concurrency: Max concurrent scans (default 10, can go up to 50)
        progress_callback: async function(current, total, domain, success) for progress updates
    
    Returns:
        dict with success_count, error_count, total
    """
    from tools.shopify_db import get_all_pending_store_ids
    import asyncio
    
    stores = get_all_pending_store_ids()
    if not stores:
        return {"success_count": 0, "error_count": 0, "total": 0}
    
    total = len(stores)
    success_count = 0
    error_count = 0
    current = 0
    lock = asyncio.Lock()
    
    concurrency = min(concurrency, 50)
    semaphore = asyncio.Semaphore(concurrency)
    
    async def scan_with_semaphore(store):
        nonlocal success_count, error_count, current
        async with semaphore:
            try:
                success, message = await scan_store(store["id"], store["url"], proxy)
            except Exception as e:
                success = False
            
            async with lock:
                current += 1
                if success:
                    success_count += 1
                else:
                    error_count += 1
                curr_count = current
            
            if progress_callback and (curr_count % 5 == 0 or curr_count == total):
                try:
                    await progress_callback(curr_count, total, store["domain"], success)
                except:
                    pass
            
            await asyncio.sleep(0.1)
            return success
    
    batch_size = min(100, len(stores))
    for i in range(0, len(stores), batch_size):
        batch = stores[i:i + batch_size]
        tasks = [scan_with_semaphore(store) for store in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
    
    return {
        "success_count": success_count,
        "error_count": error_count,
        "total": total
    }
