#!/usr/bin/env python3
"""
Extract publishable Stripe keys from gateway_probe outputs into a structured JSON for wiring later.
Inputs: logs/gateway_probe.json and logs/gateway_probe_stripe.txt (if present)
Outputs: logs/pk_live_targets.json with entries [{url, pk_live}]
"""
import json
import os
from typing import Dict, List

PROBE_JSON = "logs/gateway_probe.json"
STRIPE_TXT = "logs/gateway_probe_stripe.txt"
OUT_JSON = "logs/pk_live_targets.json"


def load_from_json() -> List[Dict[str, str]]:
    if not os.path.exists(PROBE_JSON):
        return []
    with open(PROBE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results", [])
    out = []
    seen = set()
    for r in results:
        url = r.get("url")
        pk = r.get("keys", {}).get("STRIPE_PK")
        if url and pk and (url, pk) not in seen:
            seen.add((url, pk))
            out.append({"url": url, "pk_live": pk})
    return out


def load_from_txt(existing: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not os.path.exists(STRIPE_TXT):
        return existing
    seen = {(e["url"], e["pk_live"]) for e in existing}
    out = list(existing)
    with open(STRIPE_TXT, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) == 2:
                url, pk = parts
                if (url, pk) not in seen:
                    seen.add((url, pk))
                    out.append({"url": url, "pk_live": pk})
    return out


def main():
    entries = load_from_json()
    entries = load_from_txt(entries)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"count": len(entries), "entries": entries}, f, indent=2)
    print(f"Saved {len(entries)} pk_live entries to {OUT_JSON}")


if __name__ == "__main__":
    main()
