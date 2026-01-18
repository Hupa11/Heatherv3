#!/usr/bin/env python3
"""
Stripe Key Extractor Tool
Automatically extracts Stripe publishable keys from merchant websites
"""

import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class StripeKeyExtractor:
    """Extract Stripe publishable keys from websites"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_from_url(self, url, deep_search=True):
        """
        Extract Stripe keys from a URL
        
        Args:
            url: Website URL to scan
            deep_search: If True, also checks JS files and checkout pages
            
        Returns:
            dict: {
                'publishable_keys': [...],
                'secret_keys': [...],  # Usually not exposed but check anyway
                'source': 'page' or 'js_file' or 'checkout'
            }
        """
        print(f"\n🔍 Scanning: {url}")
        results = {
            'publishable_keys': set(),
            'secret_keys': set(),
            'sources': []
        }
        
        try:
            # Get main page
            response = self.session.get(url, timeout=10)
            html = response.text
            
            # Pattern matching for Stripe keys
            pk_pattern = r'pk_(live|test)_[0-9a-zA-Z]{24,}'
            sk_pattern = r'sk_(live|test)_[0-9a-zA-Z]{24,}'
            
            # Search in HTML
            pk_matches = re.findall(pk_pattern, html)
            sk_matches = re.findall(sk_pattern, html)
            
            for match in pk_matches:
                full_key = 'pk_' + match
                results['publishable_keys'].add(full_key)
                results['sources'].append(('main_page', url))
                print(f"  ✅ Found PK: {full_key[:20]}...")
            
            for match in sk_matches:
                full_key = 'sk_' + match
                results['secret_keys'].add(full_key)
                print(f"  🔑 Found SK: {full_key[:20]}... (SECRET!)")
            
            if deep_search:
                # Parse HTML for JS files
                soup = BeautifulSoup(html, 'html.parser')
                
                # Check inline scripts
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        pk_in_script = re.findall(pk_pattern, script.string)
                        for match in pk_in_script:
                            full_key = 'pk_' + match
                            results['publishable_keys'].add(full_key)
                            results['sources'].append(('inline_script', url))
                            print(f"  ✅ Found PK in script: {full_key[:20]}...")
                
                # Check external JS files
                for script in scripts:
                    if script.get('src'):
                        js_url = urljoin(url, script['src'])
                        if 'stripe' in js_url.lower() or 'checkout' in js_url.lower():
                            try:
                                js_response = self.session.get(js_url, timeout=5)
                                pk_in_js = re.findall(pk_pattern, js_response.text)
                                for match in pk_in_js:
                                    full_key = 'pk_' + match
                                    results['publishable_keys'].add(full_key)
                                    results['sources'].append(('js_file', js_url))
                                    print(f"  ✅ Found PK in JS: {full_key[:20]}...")
                            except:
                                pass
                
                # Try common checkout paths
                checkout_paths = [
                    '/checkout',
                    '/cart',
                    '/my-account/add-payment-method',
                    '/my-account',
                    '/payment',
                    '/order'
                ]
                
                for path in checkout_paths:
                    try:
                        checkout_url = urljoin(url, path)
                        checkout_response = self.session.get(checkout_url, timeout=5)
                        pk_in_checkout = re.findall(pk_pattern, checkout_response.text)
                        for match in pk_in_checkout:
                            full_key = 'pk_' + match
                            results['publishable_keys'].add(full_key)
                            results['sources'].append(('checkout', checkout_url))
                            print(f"  ✅ Found PK in {path}: {full_key[:20]}...")
                        
                        if pk_in_checkout:
                            break  # Found keys, no need to check more paths
                    except:
                        pass
        
        except Exception as e:
            print(f"  ❌ Error scanning {url}: {e}")
        
        # Convert sets to lists
        results['publishable_keys'] = list(results['publishable_keys'])
        results['secret_keys'] = list(results['secret_keys'])
        
        return results
    
    def scan_multiple_sites(self, urls):
        """Scan multiple sites and return all found keys"""
        all_keys = {
            'publishable': [],
            'secret': [],
            'site_map': {}  # Maps keys to their source sites
        }
        
        for url in urls:
            result = self.extract_from_url(url, deep_search=True)
            
            for pk in result['publishable_keys']:
                if pk not in all_keys['publishable']:
                    all_keys['publishable'].append(pk)
                    all_keys['site_map'][pk] = url
            
            for sk in result['secret_keys']:
                if sk not in all_keys['secret']:
                    all_keys['secret'].append(sk)
                    all_keys['site_map'][sk] = url
        
        return all_keys


def main():
    """Main function for CLI usage"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║              🔑 Stripe Key Extractor Tool 🔑                  ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    # Known working sites
    target_sites = [
        "https://shopzone.nz",
        "https://www.balliante.com",
        "https://bigbattery.com",
        "https://www.districtpeople.com",
        "https://www.epicalarc.com",  # From StripeAuth.py
        "https://voyafly.com",  # From gatesandapi.txt
    ]
    
    extractor = StripeKeyExtractor()
    results = extractor.scan_multiple_sites(target_sites)
    
    print("\n" + "="*70)
    print("📊 EXTRACTION RESULTS")
    print("="*70)
    
    if results['publishable']:
        print(f"\n✅ Found {len(results['publishable'])} Publishable Key(s):")
        for i, pk in enumerate(results['publishable'], 1):
            site = results['site_map'].get(pk, 'Unknown')
            print(f"  {i}. {pk}")
            print(f"     Source: {site}")
    else:
        print("\n❌ No publishable keys found")
    
    if results['secret']:
        print(f"\n🔑 Found {len(results['secret'])} Secret Key(s) (DO NOT SHARE!):")
        for i, sk in enumerate(results['secret'], 1):
            site = results['site_map'].get(sk, 'Unknown')
            print(f"  {i}. {sk}")
            print(f"     Source: {site}")
    
    # Save to file
    if results['publishable'] or results['secret']:
        with open('extracted_keys.txt', 'w') as f:
            f.write("=== EXTRACTED STRIPE KEYS ===\n\n")
            f.write("PUBLISHABLE KEYS:\n")
            for pk in results['publishable']:
                f.write(f"{pk} ({results['site_map'].get(pk)})\n")
            f.write("\nSECRET KEYS:\n")
            for sk in results['secret']:
                f.write(f"{sk} ({results['site_map'].get(sk)})\n")
        
        print("\n💾 Results saved to: extracted_keys.txt")
    
    print("\n" + "="*70)
    print("✅ Extraction Complete!")
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    main()
