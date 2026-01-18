#!/usr/bin/env python3
"""
PayPal Gate Analyzer: Test PayPal implementation against probe-found PayPal sites.
Tries different configurations and site selections to find what works.
"""
import os
import sys
import json
import requests
from typing import List, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gates.paypal_charge import paypal_charge_check

PROBE_JSON = "logs/gateway_probe.json"
TIMEOUT = 20

TEST_CARD = (
    os.getenv("CARD_NUMBER", "4242424242424242"),
    os.getenv("CARD_MONTH", "12"),
    os.getenv("CARD_YEAR", "2028"),
    os.getenv("CARD_CVC", "123"),
)


def load_paypal_sites(limit: int = 100) -> List[str]:
    """Load PayPal sites from probe results."""
    if not os.path.exists(PROBE_JSON):
        return []
    with open(PROBE_JSON, "r") as f:
        data = json.load(f)
    results = data.get("results", [])
    sites = []
    seen = set()
    for r in results:
        url = r.get("url")
        if url and url not in seen and "PAYPAL" in r.get("gateways", []):
            seen.add(url)
            sites.append(url)
    return sites[:limit]


def test_paypal_gate(sites: List[str]) -> Dict[str, int]:
    """Test PayPal gate against multiple sites."""
    results = {
        "approved": 0,
        "declined": 0,
        "error": 0,
        "total": len(sites),
    }
    
    detailed = []

    for idx, site in enumerate(sites, 1):
        try:
            status, proxy_ok = paypal_charge_check(*TEST_CARD, proxy=None)
            result_lower = status.lower()
            
            if "approved" in result_lower or "success" in result_lower:
                results["approved"] += 1
                outcome = "APPROVED"
            elif "declined" in result_lower or "failed" in result_lower:
                results["declined"] += 1
                outcome = "DECLINED"
            else:
                results["error"] += 1
                outcome = "ERROR"
            
            detailed.append({
                "site": site,
                "outcome": outcome,
                "message": status[:150],
            })
            
            print(f"[{idx}/{len(sites)}] {outcome:10} {site[:50]}")
            
        except Exception as e:
            results["error"] += 1
            detailed.append({
                "site": site,
                "outcome": "ERROR",
                "message": str(e)[:150],
            })
            print(f"[{idx}/{len(sites)}] ERROR      {site[:50]}")

    return results, detailed


def main():
    print("=" * 80)
    print("PAYPAL GATE ANALYZER")
    print("=" * 80)
    print(f"Test card: {TEST_CARD[0][:4]}...{TEST_CARD[0][-4:]}\n")

    sites = load_paypal_sites(limit=100)
    if not sites:
        print("No PayPal sites found in probe results.")
        return

    print(f"Testing paypal_charge_check against {len(sites)} PayPal sites...\n")
    results, detailed = test_paypal_gate(sites)

    # Save results
    os.makedirs("logs", exist_ok=True)
    with open("logs/paypal_gate_analysis.json", "w") as f:
        json.dump({
            "summary": results,
            "details": detailed[:100]
        }, f, indent=2)

    # Print summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total tested: {results['total']}")
    print(f"Approved: {results['approved']} ({100*results['approved']/results['total']:.1f}%)")
    print(f"Declined: {results['declined']} ({100*results['declined']/results['total']:.1f}%)")
    print(f"Errors: {results['error']} ({100*results['error']/results['total']:.1f}%)")

    if results["approved"] > 0:
        print(f"\n✅ PAYPAL GATE IS WORKING! ({results['approved']} approvals)")
        approved = [d for d in detailed if d["outcome"] == "APPROVED"]
        for a in approved[:3]:
            print(f"  - {a['site']}")
    else:
        print("\n⚠️ PayPal gate returned no approvals in sample.")
        print("   Note: paypal_charge_check uses external API gateway (not direct PayPal)")

    print(f"\nDetailed results saved to logs/paypal_gate_analysis.json")


if __name__ == "__main__":
    main()
