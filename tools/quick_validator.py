#!/usr/bin/env python3
"""
Quick PayPal & Shopify Gate Validator: Test against best-candidate sites.
Fast, focused testing on high-confidence targets.
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gates.paypal_charge import paypal_charge_check
from gates.shopify_nano import shopify_nano_check

TEST_CARD = (
    os.getenv("CARD_NUMBER", "4242424242424242"),
    os.getenv("CARD_MONTH", "12"),
    os.getenv("CARD_YEAR", "2028"),
    os.getenv("CARD_CVC", "123"),
)

# High-value Shopify sites from probe
SHOPIFY_SITES = [
    "https://camberkits.myshopify.com",
    "https://turningpointe.myshopify.com",
    "https://dejey.myshopify.com",
]

# PayPal sites from probe
PAYPAL_SITES = [
    "https://camberkits.myshopify.com",
    "https://turningpointe.myshopify.com",
    "https://fdbf.myshopify.com",
]


def main():
    print("=" * 80)
    print("QUICK PAYPAL & SHOPIFY VALIDATOR")
    print("=" * 80)
    print(f"Test card: {TEST_CARD[0][:4]}...{TEST_CARD[0][-4:]}\n")

    results = {"paypal": [], "shopify": []}

    # Test PayPal
    print("Testing PayPal Gate")
    print("-" * 80)
    for site in PAYPAL_SITES:
        try:
            status, proxy_ok = paypal_charge_check(*TEST_CARD, proxy=None)
            result_str = status[:100]
            if "approved" in status.lower():
                result = "PASS"
            elif "declined" in status.lower():
                result = "WARN"
            else:
                result = "FAIL"
            results["paypal"].append({"site": site, "status": result, "msg": result_str})
            print(f"[{result:4}] {site}")
            print(f"       {result_str}")
        except Exception as e:
            results["paypal"].append({"site": site, "status": "FAIL", "msg": str(e)[:100]})
            print(f"[FAIL] {site}")
            print(f"       {str(e)[:80]}")

    # Test Shopify
    print("\n\nTesting Shopify Gate")
    print("-" * 80)
    for site in SHOPIFY_SITES:
        try:
            status, proxy_ok = shopify_nano_check(*TEST_CARD, shopify_site=site, proxy=None, timeout=15)
            result_str = status[:100]
            if "checkout" in status.lower() or "session" in status.lower():
                result = "PASS"
            elif "error" in status.lower() or "failed" in status.lower():
                result = "FAIL"
            else:
                result = "WARN"
            results["shopify"].append({"site": site, "status": result, "msg": result_str})
            print(f"[{result:4}] {site}")
            print(f"       {result_str}")
        except Exception as e:
            results["shopify"].append({"site": site, "status": "FAIL", "msg": str(e)[:100]})
            print(f"[FAIL] {site}")
            print(f"       {str(e)[:80]}")

    # Save results
    os.makedirs("logs", exist_ok=True)
    with open("logs/quick_validator.json", "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    pp_pass = sum(1 for r in results["paypal"] if r["status"] == "PASS")
    sp_pass = sum(1 for r in results["shopify"] if r["status"] == "PASS")
    print(f"PayPal: {pp_pass}/{len(results['paypal'])} working")
    print(f"Shopify: {sp_pass}/{len(results['shopify'])} working")
    print(f"\nResults saved to logs/quick_validator.json")


if __name__ == "__main__":
    main()
