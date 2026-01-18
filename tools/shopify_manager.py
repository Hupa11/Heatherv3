"""
Shopify Site Manager
Manages the 15000+ Shopify stores for testing
Enhanced with intelligent rotation, caching, and dead store removal
"""

import random
import os
import json
import time
import threading
import asyncio
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

SHOPIFY_FILE = "/home/null/Documents/Stacy/Stacy/FilesToLookAt/newfilestolookat/15000ShopifyGates"
CACHE_FILE = "/home/null/Documents/Stacy/Stacy/.shopify_cache.json"
DEAD_STORES_FILE = "/home/null/Documents/Stacy/Stacy/.shopify_dead.json"
BAD_STORES_FILE = "/home/null/Documents/Stacy/Stacy/.shopify_bad.json"

# Cache settings
CACHE_DURATION = 3600  # 1 hour
ENTRY_EXPIRY = 604800  # 7 days (604800 seconds) - entries older than this are pruned
TEST_BATCH_SIZE = 50   # Test 50 stores at a time
MAX_DEAD_STORES = 500  # Maximum dead stores to track
FAIL_THRESHOLD = 3     # Failures before marking store bad

# Thread-safe lock for cache operations
_cache_lock = threading.Lock()

# Async lock for concurrent async operations (created lazily)
_async_lock = None

def _get_async_lock():
    """Get or create the async lock (handles event loop changes)"""
    global _async_lock
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            _async_lock = None
        elif _async_lock is None:
            _async_lock = asyncio.Lock()
    except RuntimeError:
        _async_lock = None
    return _async_lock

# In-memory cache
_store_cache = {
    'working_stores': [],
    'last_updated': 0,
    'rotation_index': 0,
    'dead_stores': {},  # Changed to dict: {store_url: timestamp}
    'bad_counts': {}    # Changed to dict: {store_url: {'count': int, 'timestamp': float}}
}

def _load_cache():
    """Load cache from disk with automatic expiration of old entries"""
    global _store_cache
    current_time = time.time()
    
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                _store_cache['working_stores'] = data.get('working_stores', [])
                _store_cache['last_updated'] = data.get('last_updated', 0)
                _store_cache['rotation_index'] = data.get('rotation_index', 0)
                # Convert bad_counts to new format if needed (handle legacy format)
                bad_counts_raw = data.get('bad_counts', {})
                _store_cache['bad_counts'] = {}
                for store_url, value in bad_counts_raw.items():
                    if isinstance(value, dict):
                        # Already new format
                        _store_cache['bad_counts'][store_url] = value
                    else:
                        # Legacy format (just count), add current timestamp
                        _store_cache['bad_counts'][store_url] = {
                            'count': value,
                            'timestamp': current_time
                        }
    except (ValueError, IOError, KeyError) as e:
        pass
    
    try:
        if os.path.exists(DEAD_STORES_FILE):
            with open(DEAD_STORES_FILE, 'r') as f:
                data = json.load(f)
                dead_stores_raw = data.get('dead_stores', [])
                _store_cache['dead_stores'] = {}
                for item in dead_stores_raw:
                    if isinstance(item, dict):
                        # New format: {'url': ..., 'timestamp': ...}
                        _store_cache['dead_stores'][item.get('url', item)] = item.get('timestamp', current_time)
                    elif isinstance(item, str):
                        # Legacy format: just URL string
                        _store_cache['dead_stores'][item] = current_time
    except (ValueError, IOError, KeyError) as e:
        pass

    try:
        if os.path.exists(BAD_STORES_FILE):
            with open(BAD_STORES_FILE, 'r') as f:
                data = json.load(f)
                bad_counts_raw = data.get('bad_counts', {})
                for store_url, value in bad_counts_raw.items():
                    if isinstance(value, dict):
                        _store_cache['bad_counts'][store_url] = value
                    else:
                        _store_cache['bad_counts'][store_url] = {
                            'count': value,
                            'timestamp': current_time
                        }
    except (ValueError, IOError, KeyError) as e:
        pass
    
    # Prune expired entries from bad_counts
    expired_stores = []
    for store_url, entry in list(_store_cache['bad_counts'].items()):
        entry_time = entry.get('timestamp', current_time) if isinstance(entry, dict) else current_time
        if current_time - entry_time > ENTRY_EXPIRY:
            expired_stores.append(store_url)
    
    for store_url in expired_stores:
        _store_cache['bad_counts'].pop(store_url, None)
    
    # Prune expired entries from dead_stores (keep only recent ones)
    expired_dead = []
    for store_url, timestamp in list(_store_cache['dead_stores'].items()):
        if current_time - timestamp > ENTRY_EXPIRY:
            expired_dead.append(store_url)
    
    for store_url in expired_dead:
        _store_cache['dead_stores'].pop(store_url, None)

def _save_cache():
    """Save cache to disk with timestamps for expiration tracking"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'working_stores': _store_cache['working_stores'],
                'last_updated': _store_cache['last_updated'],
                'rotation_index': _store_cache['rotation_index'],
                'bad_counts': _store_cache.get('bad_counts', {})
            }, f)
    except IOError as e:
        pass
    
    try:
        # Save dead stores with timestamps
        dead_stores_list = []
        for store_url, timestamp in _store_cache['dead_stores'].items():
            dead_stores_list.append({'url': store_url, 'timestamp': timestamp})
        
        # Limit to prevent file bloat (keep most recent MAX_DEAD_STORES)
        dead_stores_list = sorted(dead_stores_list, key=lambda x: x['timestamp'], reverse=True)[:MAX_DEAD_STORES]
        
        with open(DEAD_STORES_FILE, 'w') as f:
            json.dump({'dead_stores': dead_stores_list}, f)
    except IOError as e:
        pass

    try:
        with open(BAD_STORES_FILE, 'w') as f:
            json.dump({'bad_counts': _store_cache.get('bad_counts', {})}, f)
    except IOError as e:
        pass

def load_shopify_sites(exclude_dead=True):
    """Load all Shopify sites from database first, then file as fallback"""
    sites = []
    
    try:
        from tools.shopify_db import get_ready_store_urls
        db_sites = get_ready_store_urls()
        if db_sites:
            sites = db_sites
    except Exception:
        pass
    
    if not sites:
        try:
            with open(SHOPIFY_FILE, 'r') as f:
                sites = [line.strip() for line in f if line.strip()]
        except IOError:
            pass
    
    if exclude_dead and sites:
        sites = [s for s in sites if s not in _store_cache['dead_stores']]
    
    return sites

def get_random_shopify_site(count=1):
    """Get random Shopify site(s) - backward compatible"""
    sites = load_shopify_sites()
    if not sites:
        return get_working_shopify_sites()[0] if count == 1 else get_working_shopify_sites()[:count]
    
    if count == 1:
        return random.choice(sites)
    else:
        return random.sample(sites, min(count, len(sites)))

def get_next_shopify_site():
    """
    Get next Shopify site in rotation (intelligent round-robin)
    Uses cached working stores and rotates through them
    """
    with _cache_lock:
        _load_cache()
        
        # Check if cache is stale or empty
        if (time.time() - _store_cache['last_updated'] > CACHE_DURATION or 
            not _store_cache['working_stores']):
            _refresh_working_stores()
        
        # Get next store from rotation
        if _store_cache['working_stores']:
            index = _store_cache['rotation_index']
            store = _store_cache['working_stores'][index]
            
            # Update rotation index (circular)
            _store_cache['rotation_index'] = (index + 1) % len(_store_cache['working_stores'])
            _save_cache()
            
            return store
        
        # Fallback to known working sites
        return get_working_shopify_sites()[0]


async def get_next_shopify_site_async():
    """
    Async-safe version of get_next_shopify_site()
    Uses asyncio.Lock for concurrent async operations
    """
    lock = _get_async_lock()
    if lock:
        try:
            async with lock:
                return get_next_shopify_site()
        except (RuntimeError, ValueError):
            # If async context fails, fall back to sync version
            return get_next_shopify_site()
    else:
        # No async loop, use sync version
        return get_next_shopify_site()

def _refresh_working_stores():
    """Refresh the working stores cache by testing a batch"""
    all_sites = load_shopify_sites(exclude_dead=True)
    
    if not all_sites:
        _store_cache['working_stores'] = get_working_shopify_sites()
        _store_cache['last_updated'] = time.time()
        return
    
    # Test a random batch
    batch = random.sample(all_sites, min(TEST_BATCH_SIZE, len(all_sites)))
    working = []
    
    import requests
    for site in batch:
        try:
            response = requests.get(site, timeout=5, verify=False)
            if response.status_code == 200:
                working.append(site)
            else:
                _store_cache['dead_stores'][site] = time.time()
        except (requests.RequestException, requests.Timeout) as e:
            _store_cache['dead_stores'][site] = time.time()
    
    # Update cache
    if working:
        _store_cache['working_stores'] = working
    else:
        _store_cache['working_stores'] = get_working_shopify_sites()
    
    _store_cache['last_updated'] = time.time()
    _store_cache['rotation_index'] = 0

def mark_store_dead(store_url):
    """Mark a store as dead/non-working with timestamp"""
    with _cache_lock:
        _load_cache()
        _store_cache['dead_stores'][store_url] = time.time()
        # Initialize failure count if not present
        if store_url not in _store_cache['bad_counts']:
            _store_cache['bad_counts'][store_url] = {'count': FAIL_THRESHOLD, 'timestamp': time.time()}
        
        # Remove from working stores if present
        if store_url in _store_cache['working_stores']:
            _store_cache['working_stores'].remove(store_url)
        
        _save_cache()

def mark_store_working(store_url):
    """Mark a store as working (remove from dead list)"""
    with _cache_lock:
        _load_cache()
        
        # Remove from dead stores if present
        if store_url in _store_cache['dead_stores']:
            _store_cache['dead_stores'].pop(store_url, None)
        
        # Remove from bad_counts if present
        if store_url in _store_cache.get('bad_counts', {}):
            _store_cache['bad_counts'].pop(store_url, None)
        
        # Add to working stores if not present
        if store_url not in _store_cache['working_stores']:
            _store_cache['working_stores'].append(store_url)
        
        _save_cache()


def mark_store_failure(store_url):
    """Increment failure count; mark dead when threshold exceeded."""
    with _cache_lock:
        _load_cache()
        current_time = time.time()
        
        counts = _store_cache.setdefault('bad_counts', {})
        
        # Initialize or update entry
        if store_url not in counts:
            counts[store_url] = {'count': 1, 'timestamp': current_time}
        else:
            entry = counts[store_url]
            if isinstance(entry, dict):
                entry['count'] = entry.get('count', 0) + 1
                entry['timestamp'] = current_time
            else:
                # Legacy format, convert to new
                counts[store_url] = {'count': entry + 1, 'timestamp': current_time}
        
        # Mark as dead if threshold exceeded
        if counts[store_url].get('count', 0) >= FAIL_THRESHOLD:
            _store_cache['dead_stores'][store_url] = current_time
            if store_url in _store_cache['working_stores']:
                _store_cache['working_stores'].remove(store_url)
        
        _save_cache()

def get_working_shopify_sites():
    """Return known working Shopify sites"""
    return [
        "https://voyafly.com",
        "https://shopzone.nz",
        "https://nanoscc.com"
    ]

def test_shopify_site(site_url, timeout=10):
    """
    Test if a Shopify site is responsive
    
    Args:
        site_url: URL of the Shopify site
        timeout: Request timeout in seconds
    
    Returns:
        tuple: (is_working, response_time, status_code)
    """
    import requests
    import time
    
    try:
        start = time.time()
        response = requests.get(site_url, timeout=timeout, verify=False)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            return (True, elapsed, response.status_code)
        else:
            return (False, elapsed, response.status_code)
    except Exception as e:
        return (False, 0, 0)


def advanced_shopify_health(site_url, timeout=10):
    """Advanced checker: fetch products.json and basic page to validate catalog readiness."""
    import requests
    site_url = site_url.rstrip('/')
    product_url = f"{site_url}/products.json?limit=1"
    try:
        prod_resp = requests.get(product_url, timeout=timeout, verify=False)
        prod_ok = prod_resp.status_code == 200 and bool(prod_resp.json().get('products', []))
    except Exception:
        prod_ok = False
    simple_ok, elapsed, status_code = test_shopify_site(site_url, timeout)
    return {
        'site': site_url,
        'html_ok': simple_ok,
        'status_code': status_code,
        'products_ok': prod_ok,
        'checked_at': time.time()
    }

def get_cache_stats():
    """Get statistics about the cache"""
    with _cache_lock:
        _load_cache()
        
        return {
            'working_stores_count': len(_store_cache['working_stores']),
            'dead_stores_count': len(_store_cache['dead_stores']),
            'bad_stores_tracked': len(_store_cache.get('bad_counts', {})),
            'last_updated': datetime.fromtimestamp(_store_cache['last_updated']).strftime('%Y-%m-%d %H:%M:%S') if _store_cache['last_updated'] > 0 else 'Never',
            'rotation_index': _store_cache['rotation_index'],
            'cache_age_seconds': time.time() - _store_cache['last_updated'],
            'is_stale': time.time() - _store_cache['last_updated'] > CACHE_DURATION
        }

def clear_cache():
    """Clear all cache data"""
    with _cache_lock:
        _store_cache['working_stores'] = []
        _store_cache['last_updated'] = 0
        _store_cache['rotation_index'] = 0
        _store_cache['dead_stores'] = {}
        _store_cache['bad_counts'] = {}
        _save_cache()

def bulk_test_stores(count=100, timeout=5):
    """
    Test a batch of stores and update cache
    
    Args:
        count: Number of stores to test
        timeout: Request timeout per store
    
    Returns:
        dict: Statistics about tested stores
    """
    import requests
    
    all_sites = load_shopify_sites(exclude_dead=True)
    if not all_sites:
        return {'error': 'No stores available to test'}
    
    batch = random.sample(all_sites, min(count, len(all_sites)))
    
    stats = {
        'tested': 0,
        'working': 0,
        'dead': 0,
        'working_stores': []
    }
    
    for site in batch:
        is_working, elapsed, status = test_shopify_site(site, timeout)
        stats['tested'] += 1
        
        if is_working:
            stats['working'] += 1
            stats['working_stores'].append(site)
            mark_store_working(site)
        else:
            stats['dead'] += 1
            mark_store_dead(site)
    
    return stats

if __name__ == "__main__":
    print("Shopify Site Manager - Enhanced Edition")
    print("="*60)
    
    sites = load_shopify_sites()
    print(f"\n📦 Loaded {len(sites)} Shopify sites from database")
    
    print("\n📊 Cache Statistics:")
    stats = get_cache_stats()
    for key, value in stats.items():
        print(f"  • {key}: {value}")
    
    print("\n🎲 Random sample (10 sites):")
    for site in get_random_shopify_site(10):
        print(f"  • {site}")
    
    print("\n✅ Known working sites:")
    for site in get_working_shopify_sites():
        print(f"  • {site}")
    
    print("\n🔄 Testing intelligent rotation:")
    print("  Getting 5 sites using round-robin rotation:")
    for i in range(5):
        site = get_next_shopify_site()
        print(f"  {i+1}. {site}")
    
    print("\n💡 Tip: Use get_next_shopify_site() for intelligent rotation")
    print("   Use get_random_shopify_site() for random selection")
