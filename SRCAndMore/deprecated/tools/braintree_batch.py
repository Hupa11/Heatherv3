#!/usr/bin/env python3
"""
Batch runner for Braintree checker using probe results.
- Reads Braintree targets from logs/gateway_probe.json
- Runs gates.braintree_check per site (store_url passed through)
- Writes summary to logs/braintree_batch.log and logs/braintree_batch.json

Env vars:
  CARD_NUMBER, CARD_MONTH, CARD_YEAR, CARD_CVC   # defaults to 4242 test card
  BRAINTREE_BATCH_LIMIT (int)                    # max sites to process (default 8)
  BRAINTREE_BATCH_OFFSET (int)                   # skip first N sites (default 0)
  BRAINTREE_TIMEOUT (int)                        # request timeout (default 25)
"""
import json
import os
import sys
import time
from typing import List, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from gates.braintree import braintree_check  # type: ignore

LOG_DIR = "logs"
PROBE_JSON = "logs/gateway_probe.json"
LOG_TEXT = os.path.join(LOG_DIR, "braintree_batch.log")
LOG_JSON = os.path.join(LOG_DIR, "braintree_batch.json")


def load_braintree_sites(limit: int, offset: int) -> List[str]:
    if not os.path.exists(PROBE_JSON):
        raise FileNotFoundError(f"Probe results not found: {PROBE_JSON}")
    with open(PROBE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    results: List[Dict] = data.get("results", [])
    sites = []
    seen = set()
    for r in results:
        url = r.get("url")
        if not url or url in seen:
            continue
        gateways = r.get("gateways", [])
        keys = r.get("keys", {})
        if "BRAINTREE" in gateways or keys.get("BRAINTREE_TOKEN"):
            seen.add(url)
            sites.append(url)
    return sites[offset:offset + limit]


def run_batch():
    limit = int(os.getenv("BRAINTREE_BATCH_LIMIT", "8"))
    offset = int(os.getenv("BRAINTREE_BATCH_OFFSET", "0"))
    timeout = int(os.getenv("BRAINTREE_TIMEOUT", "25"))
    proxy = os.getenv("PROXY")  # format: host:port:user:pass or host:port
    card_num = os.getenv("CARD_NUMBER", "4242424242424242")
    card_mon = os.getenv("CARD_MONTH", "12")
    card_yer = os.getenv("CARD_YEAR", "2028")
    card_cvc = os.getenv("CARD_CVC", "123")
    if proxy:
        print(f"Using proxy: {proxy.split(':')[0]}:{proxy.split(':')[1]}")

    sites = load_braintree_sites(limit=limit, offset=offset)
    print(f"Processing {len(sites)} Braintree targets (offset={offset}, limit={limit})")

    os.makedirs(LOG_DIR, exist_ok=True)
    entries = []
    start = time.time()

    for idx, site in enumerate(sites, 1):
        try:
            proxy_dict = None
            if proxy:
                parts = proxy.split(":")
                if len(parts) == 4:
                    proxy_dict = {
                        "http": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}",
                        "https": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                    }
                elif len(parts) == 2:
                    proxy_dict = {
                        "http": f"http://{parts[0]}:{parts[1]}",
                        "https": f"http://{parts[0]}:{parts[1]}"
                    }
            status, proxy_live = braintree_check(card_num, card_mon, card_yer, card_cvc, store_url=site, proxy=proxy_dict, timeout=timeout)
            entries.append({
                "site": site,
                "status": status,
                "proxy_live": proxy_live,
            })
            print(f"[{idx}/{len(sites)}] {site}\n  {status}")
        except Exception as e:
            entries.append({
                "site": site,
                "status": f"Error: {str(e)[:160]}",
                "proxy_live": False,
            })
            print(f"[{idx}/{len(sites)}] {site}\n  Error: {e}")

    elapsed = round(time.time() - start, 2)
    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": {"count": len(entries), "elapsed_sec": elapsed}, "entries": entries}, f, indent=2)
    with open(LOG_TEXT, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(f"{e['site']}\t{e['status']}\n")
    print(f"Saved batch log to {LOG_JSON} ({elapsed}s)")


if __name__ == "__main__":
    run_batch()
