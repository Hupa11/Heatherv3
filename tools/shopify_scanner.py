"""
Shopify Site Scanner
Scans multiple Shopify sites to find ones with working checkout flows
for payment validation
"""

import requests
import concurrent.futures
import json
import re
import time
from typing import List, Tuple, Dict, Optional
import random


def _normalize_url(url: str) -> str:
    """Normalize URL to standard format"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    return url.rstrip('/')


def _check_site_status(url: str, timeout: int = 10, check_stripe: bool = True) -> Dict:
    """
    Check if a Shopify site is accessible, has products, and has Stripe integration
    
    Returns dict with:
    - url: normalized URL
    - status: 'working', 'working_stripe', 'no_products', 'error', 'timeout'
    - product_count: number of products found
    - cheapest_product: info about cheapest product if found
    - has_stripe: True if Stripe integration detected
    - stripe_pk: Stripe publishable key if found
    - error: error message if any
    """
    result = {
        'url': url,
        'status': 'error',
        'product_count': 0,
        'cheapest_product': None,
        'has_stripe': False,
        'stripe_pk': None,
        'error': None
    }
    
    try:
        url = _normalize_url(url)
        result['url'] = url
        
        products_url = f"{url}/products.json?limit=250"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        
        response = requests.get(products_url, headers=headers, timeout=timeout, allow_redirects=True)
        
        if response.status_code == 404:
            result['status'] = 'no_api'
            result['error'] = 'Products API not accessible'
            return result
        
        if response.status_code == 403:
            result['status'] = 'blocked'
            result['error'] = 'Access blocked'
            return result
        
        if response.status_code != 200:
            result['status'] = 'error'
            result['error'] = f'HTTP {response.status_code}'
            return result
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            result['status'] = 'no_api'
            result['error'] = 'Invalid JSON response'
            return result
        
        products = data.get('products', [])
        result['product_count'] = len(products)
        
        if not products:
            result['status'] = 'no_products'
            return result
        
        cheapest = None
        cheapest_price = float('inf')
        
        for product in products:
            variants = product.get('variants', [])
            for variant in variants:
                if not variant.get('available', False):
                    continue
                
                price_str = variant.get('price', '0')
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue
                
                if price > 0 and price < cheapest_price:
                    cheapest_price = price
                    cheapest = {
                        'title': product.get('title', 'Unknown'),
                        'variant_id': variant.get('id'),
                        'price': price,
                        'sku': variant.get('sku', ''),
                    }
        
        if cheapest:
            result['cheapest_product'] = cheapest
            result['status'] = 'working'
            
            if check_stripe and cheapest and cheapest.get('variant_id'):
                session = requests.Session()
                session.headers.update(headers)
                
                try:
                    cart_add_url = f"{url}/cart/add.js"
                    cart_data = {
                        'id': cheapest['variant_id'],
                        'quantity': 1
                    }
                    cart_resp = session.post(cart_add_url, data=cart_data, timeout=timeout)
                    
                    if cart_resp.status_code == 200:
                        checkout_url = f"{url}/checkout"
                        checkout_resp = session.get(checkout_url, timeout=timeout, allow_redirects=True)
                        
                        if checkout_resp.status_code == 200:
                            checkout_text = checkout_resp.text
                            
                            pk_match = re.search(r'pk_(live|test)_[a-zA-Z0-9]{20,}', checkout_text)
                            if pk_match:
                                result['has_stripe'] = True
                                result['stripe_pk'] = pk_match.group(0)
                                result['status'] = 'working_stripe'
                            elif 'js.stripe.com' in checkout_text or 'stripe.js' in checkout_text.lower():
                                result['has_stripe'] = True
                                result['status'] = 'working_stripe'
                            elif 'stripe_card_payment' in checkout_text.lower() or 'data-stripe' in checkout_text.lower():
                                result['has_stripe'] = True
                                result['status'] = 'working_stripe'
                except:
                    pass
                
                if not result['has_stripe']:
                    try:
                        home_resp = requests.get(url, headers=headers, timeout=timeout//2, allow_redirects=True)
                        if home_resp.status_code == 200:
                            home_text = home_resp.text
                            pk_match = re.search(r'pk_(live|test)_[a-zA-Z0-9]{20,}', home_text)
                            if pk_match:
                                result['has_stripe'] = True
                                result['stripe_pk'] = pk_match.group(0)
                                result['status'] = 'working_stripe'
                            elif 'js.stripe.com' in home_text:
                                result['has_stripe'] = True
                                result['status'] = 'working_stripe'
                    except:
                        pass
        else:
            result['status'] = 'no_available_products'
            result['error'] = 'No available products with price > 0'
        
        return result
        
    except requests.exceptions.Timeout:
        result['status'] = 'timeout'
        result['error'] = 'Request timeout'
        return result
    except requests.exceptions.RequestException as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
        return result
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
        return result


def scan_sites(urls: List[str], max_workers: int = 10, timeout: int = 10, 
               stop_on_first: int = 0, callback=None) -> List[Dict]:
    """
    Scan multiple Shopify sites concurrently
    
    Args:
        urls: List of Shopify store URLs
        max_workers: Max concurrent workers
        timeout: Request timeout per site
        stop_on_first: Stop after finding this many working sites (0 = scan all)
        callback: Optional callback function(result) called for each result
    
    Returns:
        List of result dicts from _check_site_status
    """
    results = []
    working_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(_check_site_status, url, timeout): url for url in urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                result = future.result()
                results.append(result)
                
                if callback:
                    callback(result)
                
                if result['status'] == 'working':
                    working_count += 1
                    if stop_on_first > 0 and working_count >= stop_on_first:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                        
            except Exception as e:
                url = future_to_url[future]
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)[:50]
                })
    
    return results


def load_sites_from_file(filepath: str, limit: int = None) -> List[str]:
    """Load Shopify site URLs from file"""
    sites = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    sites.append(url)
                    if limit and len(sites) >= limit:
                        break
    except FileNotFoundError:
        return []
    return sites


def find_working_sites(filepath: str, count: int = 10, max_workers: int = 20, 
                       verbose: bool = False) -> List[Dict]:
    """
    Find a number of working Shopify sites from file
    
    Args:
        filepath: Path to file with Shopify URLs
        count: Number of working sites to find
        max_workers: Concurrent workers
        verbose: Print progress
    
    Returns:
        List of working site dicts with url, cheapest_product info
    """
    sites = load_sites_from_file(filepath)
    
    if not sites:
        if verbose:
            print(f"No sites loaded from {filepath}")
        return []
    
    if verbose:
        print(f"Loaded {len(sites)} sites, scanning for {count} working...")
    
    random.shuffle(sites)
    
    working = []
    scanned = 0
    batch_size = min(100, len(sites))
    
    while len(working) < count and scanned < len(sites):
        batch = sites[scanned:scanned + batch_size]
        scanned += len(batch)
        
        def on_result(result):
            if result['status'] == 'working' and verbose:
                print(f"  [+] {result['url']} - ${result['cheapest_product']['price']}")
        
        results = scan_sites(
            batch, 
            max_workers=max_workers, 
            timeout=10,
            stop_on_first=count - len(working),
            callback=on_result if verbose else None
        )
        
        for r in results:
            if r['status'] == 'working':
                working.append(r)
                if len(working) >= count:
                    break
        
        if verbose:
            print(f"  Scanned {scanned}/{len(sites)}, found {len(working)}/{count} working")
    
    return working[:count]


def save_working_sites(sites: List[Dict], filepath: str):
    """Save working sites to JSON file"""
    with open(filepath, 'w') as f:
        json.dump(sites, f, indent=2)


def load_working_sites(filepath: str) -> List[Dict]:
    """Load previously saved working sites"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


if __name__ == '__main__':
    import sys
    
    print("=" * 60)
    print("SHOPIFY SITE SCANNER")
    print("=" * 60)
    
    source_file = "../attached_assets/15000ShopifyGates_1768179416543"
    
    sites = load_sites_from_file(source_file, limit=50)
    print(f"\nLoaded {len(sites)} sites for test scan")
    
    print("\nScanning (first 50 sites)...")
    
    working = find_working_sites(source_file, count=5, max_workers=15, verbose=True)
    
    print(f"\n{'='*60}")
    print(f"RESULTS: Found {len(working)} working sites")
    print("=" * 60)
    
    for site in working:
        print(f"\n  URL: {site['url']}")
        if site.get('cheapest_product'):
            cp = site['cheapest_product']
            print(f"  Product: {cp['title'][:40]}")
            print(f"  Price: ${cp['price']}")
            print(f"  Variant ID: {cp['variant_id']}")
