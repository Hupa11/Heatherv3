#!/usr/bin/env python3
"""
Debug variant ID extraction from Shopify stores
"""

import sys
sys.path.insert(0, '/home/null/Documents/Stacy/Stacy')

import requests
import json
import re

urllib3_warnings = False
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except:
    pass

test_stores = [
    "https://camberkits.myshopify.com",
    "https://fdbf.myshopify.com",
    "https://turningpointe.myshopify.com"
]

def debug_variants(store_url):
    store_url = store_url.rstrip('/')
    session = requests.Session()
    session.verify = False
    
    results = {
        "store": store_url,
        "attempts": []
    }
    
    # Try products.json
    try:
        resp = session.get(f"{store_url}/products.json?limit=3", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get('products', [])
            results['attempts'].append({
                "method": "products.json",
                "status": 200,
                "products_found": len(products)
            })
            
            if products:
                product = products[0]
                variants = product.get('variants', [])
                if variants:
                    v = variants[0]
                    results['attempts'][-1]['variant_id'] = v.get('id')
                    results['attempts'][-1]['variant_available'] = v.get('available')
                    results['attempts'][-1]['variant_data'] = {
                        'id': v.get('id'),
                        'title': v.get('title'),
                        'available': v.get('available'),
                        'price': v.get('price')
                    }
    except Exception as e:
        results['attempts'].append({
            "method": "products.json",
            "error": str(e)[:100]
        })
    
    # Try direct product page
    try:
        resp = session.get(f"{store_url}/products", timeout=10)
        if resp.status_code == 200:
            # Look for variant ID in HTML
            matches = re.findall(r'"id":(\d+)(?:[,}]|")', resp.text[:5000])
            variant_matches = re.findall(r'"variant_id":(\d+)', resp.text[:5000])
            
            results['attempts'].append({
                "method": "products page HTML",
                "status": 200,
                "id_matches": len(matches),
                "variant_id_matches": len(variant_matches),
                "first_variant_id": variant_matches[0] if variant_matches else (matches[0] if matches else None)
            })
    except Exception as e:
        results['attempts'].append({
            "method": "products page HTML",
            "error": str(e)[:100]
        })
    
    # Check if store is actually accessible
    try:
        resp = session.get(store_url, timeout=10)
        results['store_accessible'] = resp.status_code == 200
        results['store_status'] = resp.status_code
    except Exception as e:
        results['store_accessible'] = False
        results['store_error'] = str(e)[:100]
    
    return results

print("Debugging Shopify variant extraction...\n")

all_results = []
for store in test_stores:
    print(f"Checking {store}...")
    result = debug_variants(store)
    all_results.append(result)
    
    print(f"  Store accessible: {result.get('store_accessible')}")
    for attempt in result.get('attempts', []):
        if 'variant_id' in attempt:
            print(f"  {attempt['method']}: variant_id={attempt['variant_id']}, available={attempt.get('variant_available')}")
        elif 'first_variant_id' in attempt:
            print(f"  {attempt['method']}: first_id={attempt['first_variant_id']}")
        elif 'error' in attempt:
            print(f"  {attempt['method']}: ERROR - {attempt['error'][:60]}")
        else:
            print(f"  {attempt['method']}: status={attempt.get('status')}")

# Save full results
with open('logs/shopify_variant_debug.json', 'w') as f:
    json.dump(all_results, f, indent=2)

print("\nFull results saved to logs/shopify_variant_debug.json")
