#!/usr/bin/env python3
"""
Gateway Audit Tool
Tests all active payment gateway functions and reports anomalies.
"""

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Tuple, Dict, Any, List, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gates.stripe import stripe_check
from gates.stripe_auth import stripe_auth_check
from gates.stripe_20 import stripe_20_check
from gates.stripe_auth_epicalarc import stripe_auth_epicalarc_check
from gates.stripe_sk_charge import stripe_sk_charge
from gates.stripe_js import stripe_js_check
from gates.braintree import braintree_check
from gates.braintree_auth import braintree_auth_check
from gates.braintree_laguna import gateway_check as braintree_laguna_check
from gates.lions_club import lions_club_check
from gates.paypal_charge import paypal_charge_check
from gates.checkout import checkout_check
from gates.checkout_auth import checkout_auth_check
from gates.woostripe import woostripe_check
from gates.woostripe_auth import woostripe_auth_check
from gates.woostripe_browser import woostripe_browser_auth as woostripe_browser_check
from gates.shopify_nano import shopify_nano_check
from gates.shopify_auto import shopify_auto_check
from gates.madystripe import madystripe_check
from gates.corrigan_charge import corrigan_check as corrigan_charge_check
from gates.tsa_charge import tsa_check as tsa_charge_check
from gates.bellalliance_charge import bellalliance_charge_check as bellalliance_check
from gates.pariyatti_auth import pariyatti_auth_check
from gates.amex_auth import amex_auth_check

TEST_CARDS = [
    ("4680056031326268", "08", "2026", "748"),
    ("4680056031017974", "06", "2028", "189"),
    ("4680056031125595", "12", "2026", "333"),
    ("4680056031308134", "09", "2034", "142"),
    ("4680056031870091", "03", "2032", "359"),
    ("4680056031340566", "02", "2027", "050"),
    ("4680056031819031", "06", "2033", "087"),
    ("4680056031938781", "08", "2026", "528"),
    ("4680056031009682", "06", "2026", "577"),
    ("4680056031235204", "05", "2033", "375"),
    ("4680056031289318", "07", "2033", "743"),
    ("4680056031444137", "08", "2031", "379"),
    ("4680056031328363", "10", "2032", "701"),
]

SYNC_GATES: Dict[str, Callable] = {
    "stripe": stripe_check,
    "stripe_auth": stripe_auth_check,
    "stripe_20": stripe_20_check,
    "stripe_epicalarc": stripe_auth_epicalarc_check,
    "stripe_sk_charge": stripe_sk_charge,
    "stripe_js": stripe_js_check,
    "braintree": braintree_check,
    "braintree_auth": braintree_auth_check,
    "braintree_laguna": braintree_laguna_check,
    "lions_club": lions_club_check,
    "paypal_charge": paypal_charge_check,
    "checkout": checkout_check,
    "checkout_auth": checkout_auth_check,
    "woostripe": woostripe_check,
    "woostripe_auth": woostripe_auth_check,
    "woostripe_browser": woostripe_browser_check,
    "shopify_nano": shopify_nano_check,
    "madystripe": madystripe_check,
    "corrigan_charge": corrigan_charge_check,
    "tsa_charge": tsa_charge_check,
    "bellalliance": bellalliance_check,
    "pariyatti_auth": pariyatti_auth_check,
    "amex_auth": amex_auth_check,
}

ASYNC_GATES: Dict[str, Callable] = {
    "shopify_auto": shopify_auto_check,
}

PROXY = os.environ.get("PROXY", "")

FAST_RESPONSE_MS = 700
TIMEOUT_MS = 30000


def get_proxy_dict():
    if not PROXY:
        return None
    return {"http": PROXY, "https": PROXY}


def run_sync_gate(gate_name: str, gate_func: Callable, card: Tuple[str, str, str, str]) -> Dict[str, Any]:
    cc, mm, yy, cvv = card
    start = time.time()
    result = {
        "gate": gate_name,
        "card": f"{cc[:6]}...{cc[-4:]}",
        "timestamp": datetime.utcnow().isoformat(),
        "response": None,
        "status": None,
        "timing_ms": 0,
        "anomaly": None,
    }
    
    try:
        proxy = get_proxy_dict()
        response = gate_func(cc, mm, yy, cvv, proxy=proxy)
        elapsed_ms = int((time.time() - start) * 1000)
        result["timing_ms"] = elapsed_ms
        
        if isinstance(response, tuple):
            result["response"] = str(response[0])
            result["proxy_ok"] = response[1] if len(response) > 1 else True
        else:
            result["response"] = str(response)
            result["proxy_ok"] = True
        
        resp_lower = result["response"].lower()
        if "approved" in resp_lower or "success" in resp_lower or "live" in resp_lower:
            result["status"] = "APPROVED"
        elif "timeout" in resp_lower:
            result["status"] = "TIMEOUT"
        elif "error" in resp_lower:
            result["status"] = "ERROR"
        else:
            result["status"] = "DECLINED"
        
        if elapsed_ms < FAST_RESPONSE_MS:
            result["anomaly"] = "FAST_RESPONSE"
        elif elapsed_ms > TIMEOUT_MS:
            result["anomaly"] = "SLOW_RESPONSE"
            
    except asyncio.TimeoutError:
        result["timing_ms"] = int((time.time() - start) * 1000)
        result["status"] = "TIMEOUT"
        result["response"] = "Request timed out"
        result["anomaly"] = "TIMEOUT"
    except Exception as e:
        result["timing_ms"] = int((time.time() - start) * 1000)
        result["status"] = "ERROR"
        result["response"] = str(e)[:200]
        result["anomaly"] = "EXCEPTION"
    
    return result


async def run_async_gate(gate_name: str, gate_func: Callable, card: Tuple[str, str, str, str]) -> Dict[str, Any]:
    cc, mm, yy, cvv = card
    start = time.time()
    result = {
        "gate": gate_name,
        "card": f"{cc[:6]}...{cc[-4:]}",
        "timestamp": datetime.utcnow().isoformat(),
        "response": None,
        "status": None,
        "timing_ms": 0,
        "anomaly": None,
    }
    
    try:
        proxy = get_proxy_dict()
        if gate_name == "shopify_auto":
            response = await gate_func("https://santamonica.myshopify.com", cc, mm, yy, cvv, proxy=proxy)
        else:
            response = await gate_func(cc, mm, yy, cvv, proxy=proxy)
        
        elapsed_ms = int((time.time() - start) * 1000)
        result["timing_ms"] = elapsed_ms
        
        if isinstance(response, tuple):
            result["response"] = str(response[0])
            result["proxy_ok"] = response[1] if len(response) > 1 else True
        else:
            result["response"] = str(response)
            result["proxy_ok"] = True
        
        resp_lower = result["response"].lower()
        if "approved" in resp_lower or "success" in resp_lower or "live" in resp_lower:
            result["status"] = "APPROVED"
        elif "timeout" in resp_lower:
            result["status"] = "TIMEOUT"
        elif "error" in resp_lower:
            result["status"] = "ERROR"
        else:
            result["status"] = "DECLINED"
        
        if elapsed_ms < FAST_RESPONSE_MS:
            result["anomaly"] = "FAST_RESPONSE"
        elif elapsed_ms > TIMEOUT_MS:
            result["anomaly"] = "SLOW_RESPONSE"
            
    except asyncio.TimeoutError:
        result["timing_ms"] = int((time.time() - start) * 1000)
        result["status"] = "TIMEOUT"
        result["response"] = "Request timed out"
        result["anomaly"] = "TIMEOUT"
    except Exception as e:
        result["timing_ms"] = int((time.time() - start) * 1000)
        result["status"] = "ERROR"
        result["response"] = str(e)[:200]
        result["anomaly"] = "EXCEPTION"
    
    return result


async def run_sync_gate_async(executor: ThreadPoolExecutor, gate_name: str, gate_func: Callable, card: Tuple[str, str, str, str]) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, run_sync_gate, gate_name, gate_func, card)


def analyze_gate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"status": "ERROR", "reason": "No results"}
    
    statuses = [r["status"] for r in results]
    timings = [r["timing_ms"] for r in results]
    anomalies = [r["anomaly"] for r in results if r["anomaly"]]
    
    avg_timing = sum(timings) / len(timings) if timings else 0
    
    all_approved = all(s == "APPROVED" for s in statuses)
    all_error = all(s == "ERROR" for s in statuses)
    all_timeout = all(s == "TIMEOUT" for s in statuses)
    all_fast = all(t < FAST_RESPONSE_MS for t in timings)
    
    if all_timeout:
        return {"status": "TIMEOUT", "reason": "All requests timed out - connectivity issue", "avg_timing": avg_timing}
    if all_error:
        return {"status": "ERROR", "reason": "All requests errored - configuration issue", "avg_timing": avg_timing}
    if all_approved:
        return {"status": "BROKEN", "reason": "All cards approved - broken validation", "avg_timing": avg_timing}
    if all_fast:
        return {"status": "BROKEN", "reason": f"All responses too fast (<{FAST_RESPONSE_MS}ms) - likely failing", "avg_timing": avg_timing}
    
    has_approved = any(s == "APPROVED" for s in statuses)
    has_declined = any(s == "DECLINED" for s in statuses)
    
    if has_approved or has_declined:
        return {"status": "WORKING", "reason": "Mixed responses indicate working gate", "avg_timing": avg_timing}
    
    return {"status": "UNKNOWN", "reason": "Unable to determine status", "avg_timing": avg_timing}


async def audit_all_gates():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "gateway_audit.json")
    
    all_results: List[Dict[str, Any]] = []
    gate_summaries: Dict[str, Dict[str, Any]] = {}
    
    test_cards = TEST_CARDS[:3]
    
    print("=" * 60)
    print("GATEWAY AUDIT TOOL")
    print(f"Testing {len(SYNC_GATES) + len(ASYNC_GATES)} gates with {len(test_cards)} cards each")
    print(f"Proxy: {'Configured' if PROXY else 'Not configured'}")
    print("=" * 60)
    print()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        for gate_name, gate_func in SYNC_GATES.items():
            print(f"[{gate_name}] Testing...", end=" ", flush=True)
            gate_results = []
            
            for card in test_cards:
                try:
                    result = await asyncio.wait_for(
                        run_sync_gate_async(executor, gate_name, gate_func, card),
                        timeout=45
                    )
                except asyncio.TimeoutError:
                    result = {
                        "gate": gate_name,
                        "card": f"{card[0][:6]}...{card[0][-4:]}",
                        "timestamp": datetime.utcnow().isoformat(),
                        "status": "TIMEOUT",
                        "response": "Audit timeout exceeded",
                        "timing_ms": 45000,
                        "anomaly": "TIMEOUT",
                    }
                
                gate_results.append(result)
                all_results.append(result)
            
            analysis = analyze_gate_results(gate_results)
            gate_summaries[gate_name] = analysis
            
            status_icon = {
                "WORKING": "✅",
                "BROKEN": "⚠️",
                "ERROR": "❌",
                "TIMEOUT": "⏱️",
                "UNKNOWN": "❓"
            }.get(analysis["status"], "❓")
            
            print(f"{status_icon} {analysis['status']} ({analysis.get('avg_timing', 0):.0f}ms avg)")
        
        for gate_name, gate_func in ASYNC_GATES.items():
            print(f"[{gate_name}] Testing...", end=" ", flush=True)
            gate_results = []
            
            for card in test_cards:
                try:
                    result = await asyncio.wait_for(
                        run_async_gate(gate_name, gate_func, card),
                        timeout=45
                    )
                except asyncio.TimeoutError:
                    result = {
                        "gate": gate_name,
                        "card": f"{card[0][:6]}...{card[0][-4:]}",
                        "timestamp": datetime.utcnow().isoformat(),
                        "status": "TIMEOUT",
                        "response": "Audit timeout exceeded",
                        "timing_ms": 45000,
                        "anomaly": "TIMEOUT",
                    }
                
                gate_results.append(result)
                all_results.append(result)
            
            analysis = analyze_gate_results(gate_results)
            gate_summaries[gate_name] = analysis
            
            status_icon = {
                "WORKING": "✅",
                "BROKEN": "⚠️",
                "ERROR": "❌",
                "TIMEOUT": "⏱️",
                "UNKNOWN": "❓"
            }.get(analysis["status"], "❓")
            
            print(f"{status_icon} {analysis['status']} ({analysis.get('avg_timing', 0):.0f}ms avg)")
    
    with open(log_file, "w") as f:
        for result in all_results:
            f.write(json.dumps(result) + "\n")
    
    print()
    print("=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)
    
    categories = {"WORKING": [], "BROKEN": [], "ERROR": [], "TIMEOUT": [], "UNKNOWN": []}
    for gate_name, analysis in gate_summaries.items():
        status = analysis.get("status", "UNKNOWN")
        categories.setdefault(status, []).append(gate_name)
    
    for status, gates in categories.items():
        if gates:
            icon = {"WORKING": "✅", "BROKEN": "⚠️", "ERROR": "❌", "TIMEOUT": "⏱️", "UNKNOWN": "❓"}.get(status, "❓")
            print(f"\n{icon} {status} ({len(gates)} gates):")
            for gate in sorted(gates):
                reason = gate_summaries[gate].get("reason", "")
                print(f"   - {gate}: {reason}")
    
    print()
    print(f"Results saved to: {log_file}")
    print(f"Total tests run: {len(all_results)}")
    
    return all_results, gate_summaries


def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(audit_all_gates())
    except KeyboardInterrupt:
        print("\nAudit interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
