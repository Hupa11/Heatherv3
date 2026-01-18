#!/usr/bin/env python3
"""
Shopify Checkout Debugger: Find working product IDs and checkout URLs from Shopify sites.
Tests actual shopify sites from probe, extracts product data, and validates checkout flow.
"""
import os
import sys
import json
import requests
from urllib.parse import urljoin
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PROBE_JSON = "logs/gateway_probe.json"
HV_TARGETS = "logs/high_value_targets.json"
TIMEOUT = 20


def get_shopify_sites() -> list:
    """Load Shopify sites from probe results."""
    if os.path.exists(HV_TARGETS):
        with open(HV_TARGETS, "r") as f:
            data = json.load(f)
        return [
            entry["url"] for entry in data.get("entries", [])
            if "SHOPIFY" in entry.get("gateways", [])
        ][:20]  # Top 20 Shopify sites
    return []


def test_shopify_site(url: str, timeout: int = TIMEOUT) -> dict:
    """Test a single Shopify site for product discovery."""
    result = {
        "url": url,
        "status": "UNKNOWN",
        "products": [],
        "variant_ids": [],
        "checkout_url": None,
    }

    try:
        # Normalize URL
        if not url.startswith("http"):
            url = f"https://{url}"
        url = url.rstrip("/")
        result["url"] = url

        # Step 1: Fetch home page
        try:
            resp = requests.get(url, timeout=timeout, verify=False, allow_redirects=True)
            if resp.status_code >= 400:
                result["status"] = f"HTTP {resp.status_code}"
                return result
            html = resp.text
        except Exception as e:
            result["status"] = f"Fetch failed: {str(e)[:60]}"
            return result

        # Step 2: Try to get products.json (Shopify standard API)
        try:
            products_url = urljoin(url, "/products.json")
            presp = requests.get(products_url, timeout=timeout, verify=False)
            if presp.status_code == 200:
                pdata = presp.json()
                products = pdata.get("products", [])
                if products:
                    result["products"] = [p.get("title", "Unknown") for p in products[:3]]
                    # Get first variant ID
                    for p in products:
                        for v in p.get("variants", []):
                            result["variant_ids"].append(v.get("id"))
                            if len(result["variant_ids"]) >= 3:
                                break
                        if len(result["variant_ids"]) >= 3:
                            break
        except Exception:
            pass

        # Step 3: Try to extract variant ID from HTML
        if not result["variant_ids"]:
            # Look for variant patterns in HTML
            variant_patterns = [
                r'"variant_id"\s*:\s*(\d+)',
                r'"id"\s*:\s*(\d+)[,}]',
                r'variant-id["\']?\s*[=:]\s*["\']?(\d+)',
            ]
            for pattern in variant_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    result["variant_ids"] = matches[:3]
                    break

        # Step 4: Check for checkout URL
        if not result["variant_ids"]:
            result["status"] = "No variants found"
            return result

        # Try to get checkout URL
        try:
            cart_url = urljoin(url, "/cart.json")
            cresp = requests.get(cart_url, timeout=timeout, verify=False)
            if cresp.status_code == 200:
                cdata = cresp.json()
                result["checkout_url"] = cdata.get("checkout_url")
        except Exception:
            pass

        result["status"] = "OK" if result["variant_ids"] else "No variants"
        return result

    except Exception as e:
        result["status"] = f"Error: {str(e)[:60]}"
        return result


def main():
    print("=" * 80)
    print("SHOPIFY CHECKOUT DEBUGGER")
    print("=" * 80)

    sites = get_shopify_sites()
    if not sites:
        print("No Shopify sites found in probe results.")
        return

    print(f"Testing {len(sites)} Shopify sites for product discovery...\n")

    results = []
    for idx, site in enumerate(sites, 1):
        result = test_shopify_site(site)
        results.append(result)
        
        status_icon = "✅" if result["status"] == "OK" else "⚠️"
        print(f"[{idx}/{len(sites)}] {status_icon} {site}")
        print(f"         Status: {result['status']}")
        if result["products"]:
            print(f"         Products: {', '.join(result['products'][:2])}")
        if result["variant_ids"]:
            print(f"         Variant IDs: {', '.join(map(str, result['variant_ids'][:2]))}")
        if result["checkout_url"]:
            print(f"         Checkout: {result['checkout_url'][:70]}...")
        print()

    # Save detailed report
    os.makedirs("logs", exist_ok=True)
    with open("logs/shopify_checkout_debug.json", "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    working = [r for r in results if r["status"] == "OK"]
    print("=" * 80)
    print(f"SUMMARY: {len(working)}/{len(sites)} Shopify sites have exploitable product flows")
    if working:
        print("\nWorking sites:")
        for r in working[:5]:
            print(f"  - {r['url']} (variants: {len(r['variant_ids'])})")
    print(f"\nDetailed report saved to logs/shopify_checkout_debug.json")


if __name__ == "__main__":
    main()
