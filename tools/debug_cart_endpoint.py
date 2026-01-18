#!/usr/bin/env python3
"""
Debug cart.js response to see actual checkout URL
"""

import sys
sys.path.insert(0, '/home/null/Documents/Stacy/Stacy')

import requests
import json
import re

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except:
    pass

def test_cart_endpoint(store_url):
    store_url = store_url.rstrip('/')
    session = requests.Session()
    session.verify = False
    
    results = {
        "store": store_url,
        "steps": []
    }
    
    # Step 1: Get first variant
    try:
        resp = session.get(f"{store_url}/products.json?limit=1", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get('products', [])
            if products:
                variant_id = products[0]['variants'][0]['id']
                results['steps'].append({
                    "step": "Get variant",
                    "status": 200,
                    "variant_id": variant_id
                })
                
                # Step 2: Add to cart
                try:
                    resp = session.post(
                        f"{store_url}/cart/add.js",
                        json={"id": variant_id, "quantity": 1},
                        timeout=10,
                        headers={"X-Requested-With": "XMLHttpRequest"}
                    )
                    results['steps'].append({
                        "step": "POST /cart/add.js",
                        "status": resp.status_code,
                        "response_length": len(resp.text)
                    })
                    
                    # Step 3: Get cart.json
                    try:
                        resp = session.get(f"{store_url}/cart.json", timeout=10)
                        results['steps'].append({
                            "step": "GET /cart.json",
                            "status": resp.status_code,
                            "response_length": len(resp.text)
                        })
                        
                        if resp.status_code == 200:
                            try:
                                cart = resp.json()
                                checkout_url = cart.get('checkout_url')
                                results['steps'][-1]['checkout_url'] = checkout_url
                                results['steps'][-1]['cart_items'] = len(cart.get('items', []))
                                results['steps'][-1]['cart_total'] = cart.get('total_price')
                            except:
                                results['steps'][-1]['parse_error'] = 'Failed to parse JSON'
                    except Exception as e:
                        results['steps'].append({
                            "step": "GET /cart.json",
                            "error": str(e)[:100]
                        })
                
                except Exception as e:
                    results['steps'].append({
                        "step": "POST /cart/add.js",
                        "error": str(e)[:100]
                    })
    
    except Exception as e:
        results['steps'].append({
            "step": "Get variant",
            "error": str(e)[:100]
        })
    
    return results

test_stores = [
    "https://camberkits.myshopify.com",
    "https://fdbf.myshopify.com",
    "https://turningpointe.myshopify.com"
]

print("Testing cart.js endpoints...\n")

all_results = []
for store in test_stores:
    print(f"Testing {store}...")
    result = test_cart_endpoint(store)
    all_results.append(result)
    
    for step in result['steps']:
        if 'checkout_url' in step and step['checkout_url']:
            print(f"  ✓ {step['step']}: checkout_url = {step['checkout_url'][:80]}...")
        elif 'error' in step:
            print(f"  ✗ {step['step']}: {step['error']}")
        else:
            print(f"  • {step['step']}: {step.get('status', '?')} ({step.get('response_length', 0)} bytes)")

with open('logs/cart_endpoint_debug.json', 'w') as f:
    json.dump(all_results, f, indent=2)

print("\nFull debug saved to logs/cart_endpoint_debug.json")
