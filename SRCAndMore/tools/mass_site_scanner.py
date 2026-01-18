"""
Mass Shopify Site Scanner
Scans pending stores to find 1000 working sites with:
- Alive (products.json accessible)
- Small priced products (under $50)
- Simple checkout (no login required)
"""

import asyncio
import httpx
import os
import random
import time
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
]

MAX_PRICE = 50.0
TARGET_WORKING_SITES = 1000

async def check_site(url: str, timeout: int = 15) -> Dict:
    """
    Check if a Shopify site meets criteria:
    - Alive (products.json returns 200)
    - Has products with price < $50
    - Simple checkout (no account/login required)
    """
    result = {
        'url': url,
        'status': 'error',
        'cheapest_price': None,
        'product_count': 0,
        'has_simple_checkout': False,
        'error': None
    }
    
    if not url.startswith('http'):
        url = f"https://{url}"
    url = url.rstrip('/')
    result['url'] = url
    
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json,text/html,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = await client.get(f"{url}/products.json?limit=50", headers=headers)
            
            if resp.status_code == 403:
                result['status'] = 'blocked'
                result['error'] = 'Cloudflare/Bot protection'
                return result
            
            if resp.status_code == 404:
                result['status'] = 'no_api'
                result['error'] = 'Products API disabled'
                return result
            
            if resp.status_code != 200:
                result['status'] = 'error'
                result['error'] = f'HTTP {resp.status_code}'
                return result
            
            try:
                data = resp.json()
            except:
                result['status'] = 'error'
                result['error'] = 'Invalid JSON'
                return result
            
            products = data.get('products', [])
            if not products:
                result['status'] = 'no_products'
                result['error'] = 'No products found'
                return result
            
            cheapest_price = float('inf')
            available_count = 0
            
            for product in products:
                for variant in product.get('variants', []):
                    if not variant.get('available', False):
                        continue
                    
                    try:
                        price = float(variant.get('price', 0))
                    except:
                        continue
                    
                    if price > 0:
                        available_count += 1
                        if price < cheapest_price:
                            cheapest_price = price
            
            if available_count == 0:
                result['status'] = 'no_available'
                result['error'] = 'No available products'
                return result
            
            if cheapest_price > MAX_PRICE:
                result['status'] = 'too_expensive'
                result['error'] = f'Cheapest ${cheapest_price:.2f} > ${MAX_PRICE}'
                return result
            
            home_resp = await client.get(url, headers=headers)
            home_text = home_resp.text.lower()
            
            if 'password' in home_text and ('protected' in home_text or 'enter password' in home_text):
                result['status'] = 'password_protected'
                result['error'] = 'Store is password protected'
                return result
            
            if '/account/login' in home_text and 'required' in home_text:
                result['status'] = 'login_required'
                result['error'] = 'Login required for checkout'
                return result
            
            result['status'] = 'working'
            result['cheapest_price'] = cheapest_price
            result['product_count'] = available_count
            result['has_simple_checkout'] = True
            
            return result
            
    except httpx.TimeoutException:
        result['status'] = 'timeout'
        result['error'] = 'Connection timeout'
        return result
    except httpx.ConnectError:
        result['status'] = 'error'
        result['error'] = 'Connection failed'
        return result
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
        return result


async def scan_batch(urls: List[str], concurrency: int = 20) -> List[Dict]:
    """Scan a batch of URLs concurrently"""
    semaphore = asyncio.Semaphore(concurrency)
    
    async def limited_check(url):
        async with semaphore:
            return await check_site(url)
    
    tasks = [limited_check(url) for url in urls]
    return await asyncio.gather(*tasks)


def get_pending_stores(limit: int = 5000) -> List[str]:
    """Get pending stores from database"""
    if not DATABASE_URL:
        return []
    
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        result = session.execute(
            text("SELECT url FROM shopify_stores WHERE status = 'pending' LIMIT :limit"),
            {"limit": limit}
        )
        return [row[0] for row in result.fetchall()]


def update_store_status(url: str, status: str, cheapest_price: float = None, product_count: int = 0, error: str = None):
    """Update store status in database"""
    if not DATABASE_URL:
        return
    
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        if status == 'working':
            session.execute(
                text("""
                    UPDATE shopify_stores 
                    SET status = 'ready', last_scan = NOW(), error_count = 0, last_error = NULL
                    WHERE url = :url
                """),
                {"url": url}
            )
        else:
            session.execute(
                text("""
                    UPDATE shopify_stores 
                    SET status = :status, last_scan = NOW(), error_count = error_count + 1, last_error = :error
                    WHERE url = :url
                """),
                {"url": url, "status": status, "error": error or ''}
            )
        session.commit()


def get_working_count() -> int:
    """Get count of working stores"""
    if not DATABASE_URL:
        return 0
    
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        result = session.execute(text("SELECT COUNT(*) FROM shopify_stores WHERE status = 'ready'"))
        return result.scalar() or 0


async def run_mass_scan(target: int = 1000, batch_size: int = 100, concurrency: int = 20):
    """
    Main scanner - finds target number of working sites
    """
    print(f"\n{'='*60}")
    print(f"  SHOPIFY MASS SITE SCANNER")
    print(f"  Target: {target} working sites with products < ${MAX_PRICE}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    working_count = get_working_count()
    print(f"[*] Currently have {working_count} working sites in database")
    
    if working_count >= target:
        print(f"[+] Already have {working_count} working sites. Target met!")
        return
    
    needed = target - working_count
    print(f"[*] Need to find {needed} more working sites\n")
    
    total_scanned = 0
    new_working = 0
    stats = {'working': 0, 'blocked': 0, 'timeout': 0, 'no_products': 0, 'too_expensive': 0, 'error': 0}
    
    while new_working < needed:
        pending = get_pending_stores(limit=batch_size * 2)
        
        if not pending:
            print("[!] No more pending stores to scan")
            break
        
        batch = pending[:batch_size]
        print(f"[*] Scanning batch of {len(batch)} sites...")
        
        results = await scan_batch(batch, concurrency)
        
        for result in results:
            total_scanned += 1
            status = result['status']
            
            if status == 'working':
                stats['working'] += 1
                new_working += 1
                print(f"  [+] WORKING: {result['url']} (${result['cheapest_price']:.2f}, {result['product_count']} products)")
                update_store_status(result['url'], 'working', result['cheapest_price'], result['product_count'])
            elif status == 'blocked':
                stats['blocked'] += 1
                update_store_status(result['url'], 'blocked', error=result['error'])
            elif status == 'timeout':
                stats['timeout'] += 1
                update_store_status(result['url'], 'timeout', error=result['error'])
            elif status in ['no_products', 'no_available', 'no_api']:
                stats['no_products'] += 1
                update_store_status(result['url'], status, error=result['error'])
            elif status == 'too_expensive':
                stats['too_expensive'] += 1
                update_store_status(result['url'], 'expensive', error=result['error'])
            else:
                stats['error'] += 1
                update_store_status(result['url'], 'error', error=result['error'])
        
        elapsed = time.time() - start_time
        rate = total_scanned / elapsed if elapsed > 0 else 0
        
        print(f"\n  Progress: {new_working}/{needed} working | Scanned: {total_scanned} | Rate: {rate:.1f}/sec")
        print(f"  Stats: Working={stats['working']} | Blocked={stats['blocked']} | Timeout={stats['timeout']} | NoProducts={stats['no_products']} | Expensive={stats['too_expensive']} | Error={stats['error']}")
        print()
        
        if new_working >= needed:
            break
        
        await asyncio.sleep(0.5)
    
    elapsed = time.time() - start_time
    final_count = get_working_count()
    
    print(f"\n{'='*60}")
    print(f"  SCAN COMPLETE")
    print(f"{'='*60}")
    print(f"  Total scanned: {total_scanned}")
    print(f"  New working sites found: {new_working}")
    print(f"  Total working sites in DB: {final_count}")
    print(f"  Time elapsed: {elapsed:.1f} seconds")
    print(f"  Success rate: {(stats['working']/total_scanned*100):.1f}%")
    print(f"{'='*60}\n")


def export_working_sites(output_file: str = "working_shopify_sites.txt"):
    """Export all working sites to a file"""
    if not DATABASE_URL:
        print("[!] No database configured")
        return
    
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        result = session.execute(
            text("SELECT url FROM shopify_stores WHERE status = 'ready' ORDER BY last_scan DESC")
        )
        sites = [row[0] for row in result.fetchall()]
    
    with open(output_file, 'w') as f:
        for site in sites:
            f.write(f"{site}\n")
    
    print(f"[+] Exported {len(sites)} working sites to {output_file}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_working_sites()
    else:
        asyncio.run(run_mass_scan(target=TARGET_WORKING_SITES, batch_size=100, concurrency=25))
