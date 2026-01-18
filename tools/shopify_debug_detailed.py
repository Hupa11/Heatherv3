"""
Debug Shopify checkout flow in detail.
Tests multiple checkout approaches to identify working method.
"""

import requests
import json
import re
from urllib.parse import urljoin
import sys
sys.path.insert(0, '/home/null/Documents/Stacy/Stacy')
from gates.utilities import REQUEST_TIMEOUT

def test_shopify_checkout_detailed(store_url):
    """
    Test Shopify checkout with detailed debugging
    """
    try:
        store_url = store_url.rstrip('/')
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        results = {
            "store": store_url,
            "steps": []
        }
        
        # Step 1: Get products.json
        try:
            resp = session.get(f"{store_url}/products.json", timeout=8, verify=False)
            results['steps'].append({
                "step": "Get products.json",
                "status": resp.status_code,
                "success": resp.status_code == 200
            })
            
            if resp.status_code != 200:
                return results
            
            data = resp.json()
            if not data.get('products'):
                results['steps'].append({"step": "Parse products", "success": False})
                return results
            
            product = data['products'][0]
            variant_id = product['variants'][0]['id']
            results['steps'].append({
                "step": "Parse products",
                "success": True,
                "product_id": product['id'],
                "variant_id": variant_id
            })
        except Exception as e:
            results['steps'].append({"step": "Get products", "error": str(e)})
            return results
        
        # Step 2: Try cart/add.js with POST
        try:
            resp = session.post(
                f"{store_url}/cart/add.js",
                json={"id": variant_id, "quantity": 1},
                timeout=8,
                headers={"X-Requested-With": "XMLHttpRequest"},
                verify=False
            )
            results['steps'].append({
                "step": "POST cart/add.js",
                "status": resp.status_code,
                "success": resp.status_code in [200, 201],
                "response_length": len(resp.text)
            })
        except Exception as e:
            results['steps'].append({"step": "POST cart/add.js", "error": str(e)})
        
        # Step 3: Try alternative /cart endpoints
        try:
            resp = session.post(
                f"{store_url}/cart",
                data={"form_type": "cart", "id": variant_id, "quantity": 1},
                timeout=8,
                verify=False
            )
            results['steps'].append({
                "step": "POST /cart form",
                "status": resp.status_code,
                "success": resp.status_code in [200, 201, 302],
            })
        except Exception as e:
            results['steps'].append({"step": "POST /cart form", "error": str(e)})
        
        # Step 4: Get checkout page
        try:
            resp = session.get(
                f"{store_url}/checkout",
                timeout=8,
                verify=False,
                allow_redirects=True
            )
            results['steps'].append({
                "step": "GET /checkout",
                "status": resp.status_code,
                "success": resp.status_code == 200,
                "has_paypal": 'paypal' in resp.text.lower(),
                "has_braintree": 'braintree' in resp.text.lower(),
                "has_stripe": 'stripe' in resp.text.lower(),
                "response_length": len(resp.text)
            })
        except Exception as e:
            results['steps'].append({"step": "GET /checkout", "error": str(e)})
        
        # Step 5: Try /cart.json to verify cart state
        try:
            resp = session.get(f"{store_url}/cart.json", timeout=8, verify=False)
            cart_data = resp.json()
            results['steps'].append({
                "step": "GET cart.json",
                "status": resp.status_code,
                "success": resp.status_code == 200,
                "items_in_cart": len(cart_data.get('items', [])),
                "cart_total": cart_data.get('total_price')
            })
        except Exception as e:
            results['steps'].append({"step": "GET cart.json", "error": str(e)})
        
        return results
    
    except Exception as e:
        return {"store": store_url, "error": str(e)}

def main():
    # Test Shopify sites
    test_sites = [
        "https://camberkits.myshopify.com",
        "https://fdbf.myshopify.com",
        "https://turningpointe.myshopify.com",
    ]
    
    all_results = {
        "summary": {
            "total_tested": len(test_sites)
        },
        "results": []
    }
    
    print(f"Testing {len(test_sites)} Shopify stores...\n")
    
    for site in test_sites:
        print(f"Testing {site}...")
        result = test_shopify_checkout_detailed(site)
        all_results['results'].append(result)
        
        # Print step results
        if 'steps' in result:
            for step in result['steps']:
                if step.get('success'):
                    print(f"  ✓ {step['step']}: {step.get('status', 'OK')}")
                elif 'error' in step:
                    print(f"  ✗ {step['step']}: {step['error']}")
                else:
                    print(f"  ✗ {step['step']}: {step.get('status', 'FAILED')}")
        print()
    
    # Save results
    with open('logs/shopify_checkout_debug_detailed.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print("Results saved to logs/shopify_checkout_debug_detailed.json")

if __name__ == '__main__':
    main()
