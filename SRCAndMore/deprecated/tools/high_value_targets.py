#!/usr/bin/env python3
"""
High-value target analyzer: find probe sites with multiple gateway signals.
These are most likely to have working payment flows.
"""
import json
import os
from typing import Dict, List

PROBE_JSON = "logs/gateway_probe.json"
OUT_JSON = "logs/high_value_targets.json"


def analyze_targets() -> List[Dict]:
    """Find sites with multiple gateways or card forms (high-value targets)."""
    if not os.path.exists(PROBE_JSON):
        print(f"Probe file not found: {PROBE_JSON}")
        return []

    with open(PROBE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    results = data.get("results", [])
    high_value = []

    for r in results:
        if not r:
            continue
        url = r.get("url")
        gateways = r.get("gateways", [])
        keys = r.get("keys", {})
        card_form = r.get("card_form", False)

        # Score: multiple gateways, keys, or card form
        score = len(gateways)
        if keys:
            score += 2
        if card_form:
            score += 1

        if score >= 2:  # Multiple signals = high value
            high_value.append({
                "url": url,
                "score": score,
                "gateways": gateways,
                "keys": list(keys.keys()) if keys else [],
                "card_form": card_form,
            })

    # Sort by score descending
    high_value.sort(key=lambda x: x["score"], reverse=True)

    # Save report
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"count": len(high_value), "entries": high_value[:100]}, f, indent=2)

    # Print summary
    print(f"Found {len(high_value)} high-value targets (score >= 2)")
    print(f"Top 10:")
    for idx, entry in enumerate(high_value[:10], 1):
        print(f"  [{idx}] {entry['url']} | score={entry['score']} | gateways={entry['gateways']}")
    print(f"\nSaved to {OUT_JSON}")
    return high_value


if __name__ == "__main__":
    analyze_targets()
