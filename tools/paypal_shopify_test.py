"""
Test PayPal payment flows on Shopify stores with PayPal enabled.
Tries to:
1. Find PayPal payment option on checkout
2. Capture PayPal button/checkout URL
3. Test payment form if accessible
"""

import requests
import json
import re
from urllib.parse import urljoin, urlparse
import sys
sys.path.insert(0, '/home/null/Documents/Stacy/Stacy')
from gates.utilities import REQUEST_TIMEOUT

def test_paypal_shopify(store_url):
    """Test PayPal checkout flow on a Shopify store"""
    try:
        # Add product to cart first
        store_url = store_url.rstrip('/')
        product_url = f"{store_url}/products.json"
        
        # Get products
        resp = requests.get(product_url, timeout=10, verify=False)
        if resp.status_code != 200:
            return {"status": "FAIL", "reason": "No products.json"}
        
        data = resp.json()
        if not data.get('products'):
            return {"status": "FAIL", "reason": "No products"}
        
        product = data['products'][0]
        variant_id = product['variants'][0]['id']
        
        # Add to cart
        checkout_url = f"{store_url}/cart/add.js"
        payload = {
            "id": variant_id,
            "quantity": 1
        }
        
        resp = requests.post(
            checkout_url,
            json=payload,
            timeout=10,
            headers={"X-Requested-With": "XMLHttpRequest"},
            verify=False
        )
        
        if resp.status_code not in [200, 201]:
            return {"status": "FAIL", "reason": f"Cart add failed: {resp.status_code}"}
        
        # Go to checkout
        checkout_page = f"{store_url}/checkout"
        resp = requests.get(checkout_page, timeout=10, verify=False, allow_redirects=True)
        
        if resp.status_code != 200:
            return {"status": "FAIL", "reason": f"Checkout failed: {resp.status_code}"}
        
        # Look for PayPal in response
        content = resp.text.lower()
        
        has_paypal_button = False
        has_paypal_form = False
        
        # Check for PayPal button indicators
        if 'paypal' in content:
            has_paypal_button = True
        
        # Look for payment method options
        if 'payment-method' in content or 'paymentmethod' in content:
            has_paypal_form = True
        
        # Check for Braintree (PayPal processor)
        if 'braintree' in content:
            has_paypal_form = True
        
        if has_paypal_button or has_paypal_form:
            return {
                "status": "FOUND",
                "store": store_url,
                "paypal_button": has_paypal_button,
                "paypal_form": has_paypal_form,
                "message": "PayPal checkout detected"
            }
        else:
            return {
                "status": "NOT_FOUND",
                "store": store_url,
                "message": "PayPal not in checkout flow"
            }
    
    except requests.exceptions.Timeout:
        return {"status": "TIMEOUT", "store": store_url}
    except Exception as e:
        return {"status": "ERROR", "store": store_url, "error": str(e)[:100]}

def main():
    # Load test sites from paypal batch
    with open('logs/paypal_batch.json') as f:
        data = json.load(f)
    
    sites = [e['site'] for e in data['entries'][:20]]  # Test first 20
    
    results = {
        "tested": 0,
        "found": 0,
        "not_found": 0,
        "errors": 0,
        "sites": []
    }
    
    print(f"Testing {len(sites)} PayPal Shopify sites for checkout...")
    
    for i, site in enumerate(sites, 1):
        result = test_paypal_shopify(site)
        results['sites'].append(result)
        results['tested'] += 1
        
        status = result.get('status', 'UNKNOWN')
        if status == 'FOUND':
            results['found'] += 1
            print(f"[{i}] ✓ {site}: PayPal FOUND")
        elif status == 'NOT_FOUND':
            results['not_found'] += 1
            print(f"[{i}] ✗ {site}: No PayPal detected")
        else:
            results['errors'] += 1
            print(f"[{i}] ! {site}: {status}")
    
    # Save results
    with open('logs/paypal_shopify_test.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n=== SUMMARY ===")
    print(f"Tested: {results['tested']}")
    print(f"PayPal Found: {results['found']}")
    print(f"Not Found: {results['not_found']}")
    print(f"Errors: {results['errors']}")
    print(f"\nResults saved to logs/paypal_shopify_test.json")

if __name__ == '__main__':
    main()
