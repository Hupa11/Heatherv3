#!/usr/bin/env python3
"""
Performance Profiling Tool for Phase 9

Profiles all gateways to identify bottlenecks:
- Network latency
- HTML parsing overhead
- API call delays
- Total request time

Usage:
    python3 tools/profile_gateways.py                  # Profile all gateways
    python3 tools/profile_gateways.py charge5          # Profile specific gateway
    python3 tools/profile_gateways.py --json           # Output JSON report
"""

import os
import sys
import json
import time
import statistics
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test card (Visa test card - won't charge)
TEST_CARD = "4242424242424242"
TEST_MM = "12"
TEST_YY = "25"
TEST_CVC = "123"


@dataclass
class ProfileResult:
    """Single gateway profile result"""
    gateway_name: str
    total_time: float
    status: str  # OK, WARN, FAIL, TIMEOUT
    error: Optional[str] = None
    samples: int = 1


@dataclass
class ProfileReport:
    """Complete profiling report"""
    timestamp: str
    test_card: str
    total_gateways: int
    results: List[ProfileResult]
    summary: Dict


def load_gateway_check_function(gateway_name: str):
    """Dynamically load a gateway's check function"""
    try:
        if gateway_name == 'paypal':
            from gates.paypal_charge import paypal_charge_check
            return paypal_charge_check
        elif gateway_name == 'braintree':
            from gates.braintree import braintree_check
            return braintree_check
        elif gateway_name == 'stripe':
            from gates.stripe import stripe_check
            return stripe_check
        elif gateway_name == 'stripe_20':
            from gates.stripe_20 import stripe_20_check
            return stripe_20_check
        elif gateway_name == 'stripe_auth':
            from gates.stripe_auth import stripe_auth_check
            return stripe_auth_check
        elif gateway_name == 'stripe_auth_epicalarc':
            from gates.stripe_auth_epicalarc import stripe_auth_epicalarc_check
            return stripe_auth_epicalarc_check
        elif gateway_name == 'madystripe':
            from gates.madystripe import madystripe_check
            return madystripe_check
        elif gateway_name == 'blemart':
            from gates.blemart import blemart_check
            return blemart_check
        elif gateway_name == 'districtpeople':
            from gates.districtpeople import districtpeople_check
            return districtpeople_check
        elif gateway_name == 'saintvinson_givewp':
            from gates.saintvinson_givewp import saintvinson_givewp_check
            return saintvinson_givewp_check
        elif gateway_name == 'bgddesigns':
            from gates.bgddesigns import bgddesigns_check
            return bgddesigns_check
        elif gateway_name == 'staleks_florida':
            from gates.staleks_florida import staleks_florida_check
            return staleks_florida_check
        elif gateway_name == 'ccfoundation':
            from gates.ccfoundation import ccfoundation_check
            return ccfoundation_check
        elif gateway_name == 'checkout':
            from gates.checkout import checkout_check
            return checkout_check
        elif gateway_name == 'shopify':
            from gates.shopify_nano import shopify_nano_check
            return shopify_nano_check
        elif gateway_name == 'woostripe':
            from gates.woostripe import woostripe_check
            return woostripe_check
        else:
            return None
    except Exception as e:
        print(f"❌ Failed to load {gateway_name}: {e}")
        return None


def profile_gateway(gateway_name: str, runs: int = 3, timeout: int = 45) -> ProfileResult:
    """
    Profile a single gateway with multiple runs.
    
    Returns average time and result status.
    """
    print(f"  📊 Profiling {gateway_name:25} ... ", end='', flush=True)
    
    check_func = load_gateway_check_function(gateway_name)
    if not check_func:
        print(f"❌ Cannot load function")
        return ProfileResult(gateway_name, 0, "FAIL", f"Cannot load {gateway_name}")
    
    times = []
    errors = []
    status = "OK"
    last_error = None
    
    for run_num in range(runs):
        try:
            start = time.time()
            
            # Try with timeout parameter first, then without
            try:
                result, proxy_ok = check_func(TEST_CARD, TEST_MM, TEST_YY, TEST_CVC, timeout=timeout)
            except TypeError:
                # Function doesn't accept timeout
                result, proxy_ok = check_func(TEST_CARD, TEST_MM, TEST_YY, TEST_CVC)
            
            elapsed = (time.time() - start) * 1000  # Convert to ms
            times.append(elapsed)
            
            # Check for errors
            if "APPROVED" not in result and "Declined" not in result and "ERROR" not in result:
                if elapsed > timeout * 0.9 * 1000:
                    status = "TIMEOUT"
                    last_error = f"Timeout (>{timeout}s)"
                elif "error" in result.lower() or "failed" in result.lower():
                    status = "WARN"
                    last_error = result[:100]
                    
        except Exception as e:
            error_msg = str(e)[:100]
            errors.append(error_msg)
            last_error = error_msg
            status = "FAIL" if status == "OK" else status
            times.append(timeout * 1000)  # Count as timeout
    
    if times:
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        
        # Format output
        if avg_time > 30000:
            time_display = f"{avg_time/1000:.1f}s"
            icon = "🐢"  # Turtle - very slow
        elif avg_time > 10000:
            time_display = f"{avg_time/1000:.1f}s"
            icon = "🐌"  # Snail - slow
        elif avg_time > 5000:
            time_display = f"{avg_time/1000:.1f}s"
            icon = "🚶"  # Walking - moderate
        elif avg_time > 2000:
            time_display = f"{avg_time/1000:.1f}s"
            icon = "🏃"  # Running - decent
        else:
            time_display = f"{avg_time:.0f}ms"
            icon = "⚡"  # Lightning - fast
        
        status_icon = "✅" if status == "OK" else "⚠️" if status == "WARN" else "❌"
        print(f"{status_icon} {icon} {time_display:8} ({runs} runs)")
        
        return ProfileResult(
            gateway_name=gateway_name,
            total_time=avg_time,
            status=status,
            error=last_error,
            samples=runs
        )
    else:
        print(f"❌ All runs failed")
        return ProfileResult(gateway_name, 0, "FAIL", "All runs failed", 0)


def profile_all_gateways(runs: int = 3, timeout: int = 45) -> ProfileReport:
    """Profile all available gateways"""
    
    gateways = [
        'charge1', 'charge2', 'charge3', 'charge4', 'charge5',
        'stripe', 'stripe_20', 'stripe_auth', 'stripe_auth_epicalarc',
        'madystripe', 'woostripe', 'braintree', 'checkout', 'paypal',
        'shopify'
    ]
    
    print("\n" + "="*80)
    print("GATEWAY PERFORMANCE PROFILING (Phase 9)")
    print("="*80)
    print(f"\nTest Configuration:")
    print(f"  Card:        {TEST_CARD}")
    print(f"  Runs:        {runs} per gateway")
    print(f"  Timeout:     {timeout}s")
    print(f"\nProfiler Output Legend:")
    print(f"  ✅ = OK           | ⚠️  = Warning      | ❌ = Failed")
    print(f"  ⚡ = Fast(<2s)   | 🏃 = Good(2-5s)   | 🚶 = Slow(5-10s)")
    print(f"  🐌 = VarySlow(10-30s) | 🐢 = Critical(>30s)")
    print("\n" + "-"*80)
    
    results = []
    for gateway in gateways:
        result = profile_gateway(gateway, runs=runs, timeout=timeout)
        results.append(result)
        time.sleep(0.5)  # Small delay between tests
    
    # Generate summary
    summary = generate_summary(results)
    
    report = ProfileReport(
        timestamp=datetime.now().isoformat(),
        test_card=TEST_CARD,
        total_gateways=len(results),
        results=results,
        summary=summary
    )
    
    return report


def generate_summary(results: List[ProfileResult]) -> Dict:
    """Generate summary statistics"""
    
    times = [r.total_time for r in results if r.status != "FAIL"]
    
    if not times:
        return {
            "avg_time": 0,
            "min_time": 0,
            "max_time": 0,
            "median_time": 0,
            "total_ok": 0,
            "total_warn": 0,
            "total_fail": len(results)
        }
    
    return {
        "avg_time": statistics.mean(times),
        "min_time": min(times),
        "max_time": max(times),
        "median_time": statistics.median(times),
        "total_ok": sum(1 for r in results if r.status == "OK"),
        "total_warn": sum(1 for r in results if r.status == "WARN"),
        "total_fail": sum(1 for r in results if r.status == "FAIL"),
        "total_timeout": sum(1 for r in results if r.status == "TIMEOUT")
    }


def print_report(report: ProfileReport):
    """Print formatted profiling report"""
    
    print("\n" + "="*80)
    print("PROFILING SUMMARY")
    print("="*80)
    
    # Sort by time (slowest first)
    sorted_results = sorted(report.results, key=lambda r: r.total_time, reverse=True)
    
    print(f"\nBy Speed (Slowest First):")
    print("-" * 80)
    for i, result in enumerate(sorted_results[:10], 1):
        if result.status == "FAIL":
            print(f"  {i:2}. {result.gateway_name:25} | ❌ FAILED")
        else:
            time_str = f"{result.total_time/1000:.2f}s" if result.total_time > 2000 else f"{result.total_time:.0f}ms"
            print(f"  {i:2}. {result.gateway_name:25} | {time_str:10} | {result.status}")
    
    print(f"\nStatistics:")
    print(f"  Total Gateways:      {report.total_gateways}")
    print(f"  OK:                  {report.summary['total_ok']}/{report.total_gateways}")
    print(f"  Warnings:            {report.summary['total_warn']}/{report.total_gateways}")
    print(f"  Failures:            {report.summary['total_fail']}/{report.total_gateways}")
    print(f"\nTiming Metrics:")
    
    if report.summary['avg_time'] > 0:
        avg_s = report.summary['avg_time'] / 1000
        min_s = report.summary['min_time'] / 1000
        max_s = report.summary['max_time'] / 1000
        med_s = report.summary['median_time'] / 1000
        
        print(f"  Average:             {avg_s:.2f}s")
        print(f"  Minimum:             {min_s:.2f}s")
        print(f"  Maximum:             {max_s:.2f}s")
        print(f"  Median:              {med_s:.2f}s")
    
    print(f"\nTop 5 Optimization Targets:")
    print("-" * 80)
    for i, result in enumerate(sorted_results[:5], 1):
        if result.total_time > 2000:
            time_s = result.total_time / 1000
            potential_saving = (result.total_time / report.summary['median_time'] - 1) * 100
            print(f"  {i}. {result.gateway_name:25} | {time_s:6.2f}s | "
                  f"Potential: {potential_saving:.0f}% faster than median")
    
    print("\n" + "="*80)


def save_json_report(report: ProfileReport, filename: str = ".profile_report.json"):
    """Save report to JSON file"""
    data = {
        "timestamp": report.timestamp,
        "test_card": report.test_card,
        "total_gateways": report.total_gateways,
        "results": [asdict(r) for r in report.results],
        "summary": report.summary
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Report saved to: {filename}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Profile gateway performance")
    parser.add_argument('--runs', type=int, default=3, help='Number of runs per gateway (default: 3)')
    parser.add_argument('--timeout', type=int, default=45, help='Timeout per run in seconds (default: 45)')
    parser.add_argument('--json', action='store_true', help='Save JSON report')
    parser.add_argument('--gateway', type=str, help='Profile specific gateway only')
    args = parser.parse_args()
    
    if args.gateway:
        # Profile single gateway
        result = profile_gateway(args.gateway, runs=args.runs, timeout=args.timeout)
        print_report(ProfileReport(
            timestamp=datetime.now().isoformat(),
            test_card=TEST_CARD,
            total_gateways=1,
            results=[result],
            summary={}
        ))
    else:
        # Profile all
        report = profile_all_gateways(runs=args.runs, timeout=args.timeout)
        print_report(report)
        
        if args.json:
            save_json_report(report)


if __name__ == '__main__':
    main()
