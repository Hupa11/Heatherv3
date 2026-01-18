#!/usr/bin/env python3
"""
Phase 6 Workflow Status Report
Summary of probe results, gate capabilities, and next steps.
"""
import json
import os
from pathlib import Path

def get_file_count(path: str) -> int:
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return len(data.get("entries", []))
    return 0


def main():
    print("\n" + "=" * 80)
    print("PHASE 6: GATEWAY INTEGRATION WORKFLOW STATUS")
    print("=" * 80)

    print("\n📊 PROBE RESULTS")
    print("-" * 80)
    if os.path.exists("logs/gateway_probe.json"):
        with open("logs/gateway_probe.json", "r") as f:
            probe = json.load(f)
        results = probe.get("results", [])
        print(f"  Total targets scanned: {len(results)}")
        stripe_count = sum(1 for r in results if "STRIPE" in r.get("gateways", []))
        paypal_count = sum(1 for r in results if "PAYPAL" in r.get("gateways", []))
        pk_count = sum(1 for r in results if r.get("keys", {}).get("STRIPE_PK"))
        print(f"  Stripe patterns found: {stripe_count}")
        print(f"  PayPal patterns found: {paypal_count}")
        print(f"  Stripe pk_live keys: {pk_count}")

    print("\n🎯 HIGH-VALUE TARGETS")
    print("-" * 80)
    hv_count = get_file_count("logs/high_value_targets.json")
    print(f"  Multi-gateway sites (score >= 2): {hv_count}")
    if os.path.exists("logs/high_value_targets.json"):
        with open("logs/high_value_targets.json", "r") as f:
            data = json.load(f)
        if data.get("entries"):
            print(f"  Top target: {data['entries'][0]['url']}")

    print("\n⚙️ GATE CAPABILITY TEST")
    print("-" * 80)
    if os.path.exists("logs/master_gate_test.json"):
        with open("logs/master_gate_test.json", "r") as f:
            results = json.load(f)
        pass_gates = [k for k, (s, _) in results.items() if s == "PASS"]
        warn_gates = [k for k, (s, _) in results.items() if s == "WARN"]
        fail_gates = [k for k, (s, _) in results.items() if s == "FAIL"]
        print(f"  Working (PASS): {len(pass_gates)} — {', '.join(pass_gates) if pass_gates else 'None'}")
        print(f"  Responding (WARN): {len(warn_gates)} — {', '.join(warn_gates) if warn_gates else 'None'}")
        print(f"  Broken (FAIL): {len(fail_gates)} — {', '.join(fail_gates) if fail_gates else 'None'}")

    print("\n📦 BATCH RESULTS")
    print("-" * 80)
    pp_count = get_file_count("logs/paypal_batch.json")
    bt_count = get_file_count("logs/braintree_batch.json")
    print(f"  PayPal batch (first 50): {pp_count} entries logged")
    print(f"  Braintree batch (first 8): {bt_count} entries logged")

    print("\n🔑 STRIPE KEYS")
    print("-" * 80)
    pk_count = get_file_count("logs/pk_live_targets.json")
    print(f"  Publishable keys found: {pk_count}")
    if os.path.exists("logs/pk_live_targets.json"):
        with open("logs/pk_live_targets.json", "r") as f:
            data = json.load(f)
        if data.get("entries"):
            for idx, entry in enumerate(data["entries"][:3], 1):
                print(f"    [{idx}] {entry['url']} → pk_live_...{entry['pk_live'][-12:]}")

    print("\n✅ NEXT STEPS")
    print("-" * 80)
    print("  1. Locate valid Stripe SECRET KEYS (sk_live_...)")
    print("     → Once found, set STRIPE_SECRET_KEY env var or update gates/stripe.py")
    print("")
    print("  2. Run Stripe-dependent gates against pk_live targets:")
    print("     → gates/stripe.py, gates/woostripe.py, gates/stripe_20.py")
    print("     → Use discovered pk_live keys from logs/pk_live_targets.json")
    print("")
    print("  3. Expand PayPal/Braintree batch testing:")
    print("     → PAYPAL_BATCH_LIMIT=200 python3 tools/paypal_batch.py")
    print("     → Try with PROXY=<host:port:user:pass> for better success rates")
    print("")
    print("  4. Target high-value sites for focused testing:")
    print("     → Use logs/high_value_targets.json top 20 for manual validation")
    print("")
    print("  5. Validate complete flow once SKs acquired:")
    print("     → python3 tools/master_gate_test.py (all gates)")
    print("     → python3 -m pytest -q tests/test_gateways_smoke.py (with SMOKE_NETWORK=1)")
    print("")
    print("=" * 80)


if __name__ == "__main__":
    main()
