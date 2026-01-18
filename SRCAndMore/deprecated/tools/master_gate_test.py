#!/usr/bin/env python3
"""
Master gate tester: run all gates against test card and identify which ones work.
Produces a capability matrix showing which gates succeed, warn, or fail.
"""
import os
import sys
import time
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_CARD = (
    os.getenv("CARD_NUMBER", "4242424242424242"),
    os.getenv("CARD_MONTH", "12"),
    os.getenv("CARD_YEAR", "2028"),
    os.getenv("CARD_CVC", "123"),
)

PROXY = os.getenv("PROXY")
TIMEOUT = int(os.getenv("MASTER_TIMEOUT", "20"))


def test_gate(name: str, func, args=None, kwargs=None):
    """Test a single gate and return (name, status, result)."""
    if args is None:
        args = TEST_CARD
    if kwargs is None:
        kwargs = {"timeout": TIMEOUT}
    
    try:
        result = func(*args, **kwargs)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            status_str = str(result[0]).lower()
            if any(w in status_str for w in ["approved", "success", "live", "ok"]):
                return (name, "PASS", result[0][:100])
            elif any(w in status_str for w in ["error", "failed", "exception"]):
                return (name, "FAIL", result[0][:100])
            else:
                return (name, "WARN", result[0][:100])
        else:
            return (name, "WARN", f"Unexpected result type: {type(result)}")
    except Exception as e:
        return (name, "FAIL", str(e)[:100])


def main():
    print("=" * 80)
    print("MASTER GATE CAPABILITY TEST")
    print("=" * 80)
    print(f"Test card: {TEST_CARD[0][:4]}...{TEST_CARD[0][-4:]}")
    print(f"Timeout: {TIMEOUT}s")
    if PROXY:
        print(f"Proxy: {PROXY.split(':')[0]}:{PROXY.split(':')[1]}")
    print()

    results = {}
    
    # Test PayPal
    try:
        from gates.paypal_charge import paypal_charge_check
        name, status, msg = test_gate("PayPal", paypal_charge_check, kwargs={"proxy": PROXY})
        results[name] = (status, msg)
        print(f"[{status:4}] PayPal: {msg}")
    except Exception as e:
        results["PayPal"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] PayPal: {e}")

    # Test Braintree
    try:
        from gates.braintree import braintree_check
        proxy_dict = None
        if PROXY:
            parts = PROXY.split(":")
            if len(parts) == 4:
                proxy_dict = {
                    "http": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}",
                    "https": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                }
            elif len(parts) == 2:
                proxy_dict = {"http": f"http://{parts[0]}:{parts[1]}", "https": f"http://{parts[0]}:{parts[1]}"}
        name, status, msg = test_gate(
            "Braintree",
            braintree_check,
            kwargs={"store_url": "https://bigbattery.com", "proxy": proxy_dict, "timeout": TIMEOUT}
        )
        results[name] = (status, msg)
        print(f"[{status:4}] Braintree: {msg}")
    except Exception as e:
        results["Braintree"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] Braintree: {e}")

    # Test Blemart
    try:
        from gates.blemart import blemart_check
        name, status, msg = test_gate("Blemart", blemart_check, kwargs={"timeout": TIMEOUT})
        results[name] = (status, msg)
        print(f"[{status:4}] Blemart: {msg}")
    except Exception as e:
        results["Blemart"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] Blemart: {e}")

    # Test District People
    try:
        from gates.districtpeople import districtpeople_check
        name, status, msg = test_gate("District People", districtpeople_check, kwargs={"timeout": TIMEOUT})
        results[name] = (status, msg)
        print(f"[{status:4}] District People: {msg}")
    except Exception as e:
        results["District People"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] District People: {e}")

    # Test BGD Designs
    try:
        from gates.bgddesigns import bgddesigns_check
        name, status, msg = test_gate("BGD Designs", bgddesigns_check, kwargs={"timeout": TIMEOUT})
        results[name] = (status, msg)
        print(f"[{status:4}] BGD Designs: {msg}")
    except Exception as e:
        results["BGD Designs"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] BGD Designs: {e}")

    # Test Braintree Auth API
    try:
        from gates.api_gateways import braintree_auth_api_check
        name, status, msg = test_gate("BraintreeAPI", braintree_auth_api_check, kwargs={"proxy": PROXY})
        results[name] = (status, msg)
        print(f"[{status:4}] Braintree Auth API: {msg}")
    except Exception as e:
        results["BraintreeAPI"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] Braintree Auth API: {e}")

    # Test Shopify Nano
    try:
        from gates.shopify_nano import shopify_nano_check
        proxy_dict = None
        if PROXY:
            parts = PROXY.split(":")
            if len(parts) == 4:
                proxy_dict = f"{parts[0]}:{parts[1]}:{parts[2]}:{parts[3]}"
            elif len(parts) == 2:
                proxy_dict = f"{parts[0]}:{parts[1]}"
        name, status, msg = test_gate(
            "ShopifyNano",
            shopify_nano_check,
            kwargs={"shopify_site": None, "proxy": proxy_dict, "timeout": TIMEOUT}
        )
        results[name] = (status, msg)
        print(f"[{status:4}] Shopify Nano: {msg}")
    except Exception as e:
        results["ShopifyNano"] = ("FAIL", str(e)[:100])
        print(f"[FAIL] Shopify Nano: {e}")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    pass_count = sum(1 for s, _ in results.values() if s == "PASS")
    warn_count = sum(1 for s, _ in results.values() if s == "WARN")
    fail_count = sum(1 for s, _ in results.values() if s == "FAIL")
    print(f"PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count}")
    
    # Save report
    os.makedirs("logs", exist_ok=True)
    with open("logs/master_gate_test.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"Report saved to logs/master_gate_test.json")


if __name__ == "__main__":
    main()
