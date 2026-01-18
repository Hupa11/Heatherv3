"""
BIN Lookup Tool
Provides card information lookup for BIN (Bank Identification Number)
Includes caching for performance optimization
"""

import requests
import json
import time
import os
import threading
from typing import Dict, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.environ.get("BIN_CACHE_FILE", os.path.join(BASE_DIR, ".bin_cache.json"))
CACHE_DURATION = 86400  # 24 hours
MAX_CACHE_SIZE = 1000

# Thread-safe lock for cache operations
_cache_lock = threading.Lock()

# In-memory cache
_bin_cache = {}

def _load_cache():
    """Load BIN cache from disk"""
    global _bin_cache
    
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                _bin_cache = json.load(f)
    except:
        _bin_cache = {}

def _save_cache():
    """Save BIN cache to disk"""
    try:
        # Limit cache size
        if len(_bin_cache) > MAX_CACHE_SIZE:
            # Keep only the most recent entries
            sorted_items = sorted(_bin_cache.items(), key=lambda x: x[1].get('timestamp', 0), reverse=True)
            _bin_cache = dict(sorted_items[:MAX_CACHE_SIZE])
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(_bin_cache, f, indent=2)
    except:
        pass

def _is_cache_valid(bin_number: str) -> bool:
    """Check if cached BIN data is still valid"""
    if bin_number not in _bin_cache:
        return False
    
    cached_time = _bin_cache[bin_number].get('timestamp', 0)
    return (time.time() - cached_time) < CACHE_DURATION

def lookup_bin_api(bin_number: str) -> Optional[Dict]:
    """
    Lookup BIN information using free binlist.net API
    
    Args:
        bin_number: First 6-8 digits of card number
    
    Returns:
        dict: BIN information or None if lookup fails
    """
    try:
        # Normalize BIN (take first 6 digits)
        bin_number = str(bin_number)[:6]
        
        # Check cache first
        with _cache_lock:
            _load_cache()
            if _is_cache_valid(bin_number):
                return _bin_cache[bin_number]['data']
        
        # API request
        url = f"https://lookup.binlist.net/{bin_number}"
        headers = {
            'Accept-Version': '3',
            'User-Agent': 'Mozilla/5.0'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            # Cache the result
            with _cache_lock:
                _bin_cache[bin_number] = {
                    'data': data,
                    'timestamp': time.time()
                }
                _save_cache()
            
            return data
        
        return None
    
    except Exception as e:
        return None

def format_bin_info(bin_data: Dict) -> str:
    """
    Format BIN lookup data into readable string
    
    Args:
        bin_data: Dictionary from lookup_bin_api
    
    Returns:
        str: Formatted BIN information
    """
    if not bin_data:
        return "BIN info unavailable"
    
    parts = []
    
    # Card brand and type
    if 'scheme' in bin_data:
        parts.append(f"💳 {bin_data['scheme'].upper()}")
    
    if 'type' in bin_data:
        parts.append(f"({bin_data['type'].title()})")
    
    # Bank info
    if 'bank' in bin_data and bin_data['bank']:
        bank = bin_data['bank']
        if 'name' in bank:
            parts.append(f"🏦 {bank['name']}")
    
    # Country
    if 'country' in bin_data and bin_data['country']:
        country = bin_data['country']
        if 'name' in country:
            flag = country.get('emoji', '🌍')
            parts.append(f"{flag} {country['name']}")
    
    return " | ".join(parts) if parts else "BIN info unavailable"

def get_card_info(card_number: str) -> Dict:
    """
    Get comprehensive card information from BIN
    
    Args:
        card_number: Full or partial card number (minimum 6 digits)
    
    Returns:
        dict: Card information with formatted fields
    """
    bin_number = str(card_number)[:6]
    bin_data = lookup_bin_api(bin_number)
    
    if not bin_data:
        return {
            'bin': bin_number,
            'brand': 'Unknown',
            'type': 'Unknown',
            'bank': 'Unknown',
            'country': 'Unknown',
            'formatted': 'BIN info unavailable'
        }
    
    return {
        'bin': bin_number,
        'brand': bin_data.get('scheme', 'Unknown').upper(),
        'type': bin_data.get('type', 'Unknown').title(),
        'bank': bin_data.get('bank', {}).get('name', 'Unknown'),
        'country': bin_data.get('country', {}).get('name', 'Unknown'),
        'country_code': bin_data.get('country', {}).get('alpha2', 'XX'),
        'country_emoji': bin_data.get('country', {}).get('emoji', '🌍'),
        'formatted': format_bin_info(bin_data),
        'raw_data': bin_data
    }

def get_cache_stats() -> Dict:
    """Get statistics about BIN cache"""
    with _cache_lock:
        _load_cache()
        
        valid_entries = sum(1 for bin_num in _bin_cache if _is_cache_valid(bin_num))
        
        return {
            'total_entries': len(_bin_cache),
            'valid_entries': valid_entries,
            'expired_entries': len(_bin_cache) - valid_entries,
            'cache_size_kb': os.path.getsize(CACHE_FILE) / 1024 if os.path.exists(CACHE_FILE) else 0
        }

def clear_cache():
    """Clear BIN cache"""
    global _bin_cache
    with _cache_lock:
        _bin_cache = {}
        _save_cache()

def clear_expired_cache():
    """Remove expired entries from cache"""
    with _cache_lock:
        _load_cache()
        
        valid_entries = {
            bin_num: data 
            for bin_num, data in _bin_cache.items() 
            if _is_cache_valid(bin_num)
        }
        
        removed = len(_bin_cache) - len(valid_entries)
        _bin_cache = valid_entries
        _save_cache()
        
        return removed


if __name__ == "__main__":
    print("BIN Lookup Tool - Test Mode")
    print("="*60)
    
    # Test cards
    test_bins = [
        ("411111", "Visa Test Card"),
        ("542233", "Mastercard Test Card"),
        ("378282", "American Express Test Card"),
        ("601111", "Discover Test Card"),
    ]
    
    print("\n🔍 Testing BIN Lookups:\n")
    
    for bin_num, description in test_bins:
        print(f"Testing {description} ({bin_num})...")
        info = get_card_info(bin_num)
        print(f"  ✓ {info['formatted']}")
        print(f"    Brand: {info['brand']} | Type: {info['type']}")
        print(f"    Bank: {info['bank']}")
        print(f"    Country: {info['country_emoji']} {info['country']}")
        print()
    
    print("\n📊 Cache Statistics:")
    stats = get_cache_stats()
    for key, value in stats.items():
        print(f"  • {key}: {value}")
    
    print("\n✅ BIN Lookup Tool Ready!")
    print("   Usage: from tools.bin_lookup import get_card_info")
    print("   Example: info = get_card_info('4111111111111111')")
