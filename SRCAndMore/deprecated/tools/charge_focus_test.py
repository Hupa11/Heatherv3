#!/usr/bin/env python3
"""
Focused tester for charge gates (charge1-5) to identify working endpoints and best configurations.
Tests multiple store URLs and configurations for each charge gate.
"""
import os
import sys
import json
import time
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gates.blemart import blemart_check
from gates.districtpeople import districtpeople_check
from gates.bgddesigns import bgddesigns_check

TEST_CARD = (
    os.getenv("CARD_NUMBER", "4242424242424242"),
    os.getenv("CARD_MONTH", "12"),
    os.getenv("CARD_YEAR", "2028"),
    os.getenv("CARD_CVC", "123"),
)

# Known charge endpoints
CHARGE_ENDPOINTS = {
    "charge1": {"urls": ["https://blemart.com"], "func": charge1_check},
    "charge2": {"urls": ["https://storefront.com"], "func": charge2_check},
    "charge4": {"urls": ["https://bgd.io", "https://bgdomain.com"], "func": charge4_check},
}


def test_charge_gate(name: str, func, url: str = None, timeout: int = 20) -> Tuple[str, str]:
    """Test a charge gate and return (status, result_msg)."""
    try:
        if name == "charge1":
            result, proxy_ok = func(*TEST_CARD, proxy=None, timeout=timeout)
        elif name == "charge2":
            result, proxy_ok = func(*TEST_CARD, proxy=None, timeout=timeout)
        elif name == "charge4":
            result, proxy_ok = func(*TEST_CARD, proxy=None, timeout=timeout)
        else:
            result, proxy_ok = func(*TEST_CARD, timeout=timeout)
        
        result_lower = str(result).lower()
        if any(w in result_lower for w in ["approved", "success", "charged", "accepted"]):
            return ("PASS", result[:100])
        elif any(w in result_lower for w in ["declined", "failed", "error", "rejected"]):
            return ("WARN", result[:100])
        else:
            return ("WARN", result[:100])
    except Exception as e:
        return ("FAIL", str(e)[:100])


def main():
    print("=" * 80)
    print("CHARGE GATE FOCUSED TEST")
    print("=" * 80)
    print(f"Test card: {TEST_CARD[0][:4]}...{TEST_CARD[0][-4:]}")
    print()

    results = {}
    
    for gate_name, gate_info in CHARGE_ENDPOINTS.items():
        print(f"\nTesting {gate_name.upper()}")
        print("-" * 40)
        results[gate_name] = []
        
        status, msg = test_charge_gate(gate_name, gate_info["func"], timeout=20)
        results[gate_name].append({"status": status, "msg": msg})
        print(f"[{status:4}] {msg}")

    # Save report
    os.makedirs("logs", exist_ok=True)
    with open("logs/charge_gate_focus_test.json", "w") as f:
        json.dump(results, f, indent=2)
    print()
    print("=" * 80)
    print("Report saved to logs/charge_gate_focus_test.json")


if __name__ == "__main__":
    main()
