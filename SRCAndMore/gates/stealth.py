"""
Stealth Module - Anti-Detection for Gateway Requests
Provides realistic browser fingerprinting, user-agent rotation, and request timing jitter
"""

import random
import time
from typing import Dict, Optional, List
from dataclasses import dataclass

# Modern browser user agents (updated January 2026)
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Mobile Chrome
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
]

# Accept-Language headers for different locales
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-CA,en;q=0.9,fr;q=0.8",
    "en-AU,en;q=0.9",
]

# Common screen resolutions for fingerprinting
SCREEN_RESOLUTIONS = [
    (1920, 1080),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (1280, 720),
    (2560, 1440),
    (3840, 2160),
]

# Timezone offsets (minutes from UTC)
TIMEZONES = [-480, -420, -360, -300, -240, 0, 60, 120, 180, 330, 480, 540]


@dataclass
class StealthProfile:
    """A complete browser fingerprint profile"""
    user_agent: str
    accept_language: str
    screen_width: int
    screen_height: int
    timezone_offset: int
    platform: str
    webgl_vendor: str
    webgl_renderer: str
    
    def get_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """Generate realistic HTTP headers for this profile"""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none" if not referer else "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": self._get_sec_ch_ua(),
            "sec-ch-ua-mobile": "?0" if "Mobile" not in self.user_agent else "?1",
            "sec-ch-ua-platform": f'"{self.platform}"',
        }
        
        if referer:
            headers["Referer"] = referer
        
        return headers
    
    def get_api_headers(self, referer: Optional[str] = None, origin: Optional[str] = None) -> Dict[str, str]:
        """Generate headers for API/XHR requests"""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/x-www-form-urlencoded",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "sec-ch-ua": self._get_sec_ch_ua(),
            "sec-ch-ua-mobile": "?0" if "Mobile" not in self.user_agent else "?1",
            "sec-ch-ua-platform": f'"{self.platform}"',
        }
        
        if referer:
            headers["Referer"] = referer
        if origin:
            headers["Origin"] = origin
        
        return headers
    
    def _get_sec_ch_ua(self) -> str:
        """Generate sec-ch-ua header based on user agent"""
        if "Chrome/120" in self.user_agent:
            return '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        elif "Chrome/119" in self.user_agent:
            return '"Not_A Brand";v="8", "Chromium";v="119", "Google Chrome";v="119"'
        elif "Chrome/121" in self.user_agent:
            return '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"'
        elif "Firefox" in self.user_agent:
            return '"Firefox";v="121"'
        elif "Edg/" in self.user_agent:
            return '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"'
        else:
            return '"Chromium";v="120"'


# Profile cache for session persistence
_profile_cache: Dict[str, StealthProfile] = {}


def generate_profile(session_id: Optional[str] = None) -> StealthProfile:
    """
    Generate a realistic browser fingerprint profile.
    
    Args:
        session_id: Optional ID to cache/retrieve consistent profile for a session
    
    Returns:
        StealthProfile with all fingerprint data
    """
    if session_id and session_id in _profile_cache:
        return _profile_cache[session_id]
    
    user_agent = random.choice(USER_AGENTS)
    screen = random.choice(SCREEN_RESOLUTIONS)
    
    # Determine platform from user agent
    if "Windows" in user_agent:
        platform = "Windows"
        webgl_vendor = "Google Inc. (NVIDIA)"
        webgl_renderer = "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)"
    elif "Macintosh" in user_agent:
        platform = "macOS"
        webgl_vendor = "Apple Inc."
        webgl_renderer = "Apple M1 Pro"
    elif "Linux" in user_agent or "Android" in user_agent:
        platform = "Linux" if "Android" not in user_agent else "Android"
        webgl_vendor = "Google Inc. (Qualcomm)"
        webgl_renderer = "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"
    elif "iPhone" in user_agent or "iPad" in user_agent:
        platform = "iOS"
        webgl_vendor = "Apple Inc."
        webgl_renderer = "Apple GPU"
    else:
        platform = "Windows"
        webgl_vendor = "Google Inc."
        webgl_renderer = "ANGLE (Intel, Intel(R) UHD Graphics 630)"
    
    profile = StealthProfile(
        user_agent=user_agent,
        accept_language=random.choice(ACCEPT_LANGUAGES),
        screen_width=screen[0],
        screen_height=screen[1],
        timezone_offset=random.choice(TIMEZONES),
        platform=platform,
        webgl_vendor=webgl_vendor,
        webgl_renderer=webgl_renderer,
    )
    
    if session_id:
        _profile_cache[session_id] = profile
    
    return profile


def get_random_headers(referer: Optional[str] = None, origin: Optional[str] = None, api_mode: bool = False) -> Dict[str, str]:
    """
    Get random realistic headers for a request.
    
    Args:
        referer: Optional referer URL
        origin: Optional origin URL (for CORS)
        api_mode: If True, use API/XHR headers instead of page headers
    
    Returns:
        Dict of HTTP headers
    """
    profile = generate_profile()
    if api_mode:
        return profile.get_api_headers(referer=referer, origin=origin)
    return profile.get_headers(referer=referer)


def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0, jitter: float = 0.3) -> None:
    """
    Add random delay between requests to appear more human-like.
    
    Args:
        min_seconds: Minimum delay
        max_seconds: Maximum delay
        jitter: Additional random jitter factor (0-1)
    """
    base_delay = random.uniform(min_seconds, max_seconds)
    jitter_amount = base_delay * jitter * random.random()
    total_delay = base_delay + jitter_amount
    time.sleep(total_delay)


def typing_delay(text_length: int, wpm: int = 60) -> float:
    """
    Calculate realistic typing delay for form input simulation.
    
    Args:
        text_length: Number of characters to "type"
        wpm: Words per minute (average is 40-60)
    
    Returns:
        Delay in seconds
    """
    chars_per_minute = wpm * 5  # Average 5 chars per word
    base_time = (text_length / chars_per_minute) * 60
    
    # Add human variation (10-30% random deviation)
    variation = base_time * random.uniform(0.1, 0.3)
    return base_time + variation


def simulate_mouse_movement() -> List[Dict[str, int]]:
    """
    Generate realistic mouse movement coordinates for anti-bot detection.
    
    Returns:
        List of coordinate dicts with x, y positions
    """
    movements = []
    x, y = random.randint(100, 500), random.randint(100, 400)
    
    for _ in range(random.randint(5, 15)):
        dx = random.randint(-50, 50)
        dy = random.randint(-30, 30)
        x = max(0, min(1920, x + dx))
        y = max(0, min(1080, y + dy))
        movements.append({"x": x, "y": y, "timestamp": int(time.time() * 1000)})
    
    return movements


class StealthSession:
    """
    A session manager that maintains consistent fingerprinting across requests.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"session_{random.randint(10000, 99999)}"
        self.profile = generate_profile(self.session_id)
        self.request_count = 0
        self.last_request_time = 0.0
    
    def get_headers(self, referer: Optional[str] = None, origin: Optional[str] = None, api_mode: bool = False) -> Dict[str, str]:
        """Get headers with this session's consistent fingerprint"""
        if api_mode:
            return self.profile.get_api_headers(referer=referer, origin=origin)
        return self.profile.get_headers(referer=referer)
    
    def pre_request_delay(self, min_delay: float = 0.3, max_delay: float = 1.5) -> None:
        """Add delay before request if needed to avoid rate limiting"""
        if self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < min_delay:
                time.sleep(random.uniform(min_delay - elapsed, max_delay))
    
    def post_request(self) -> None:
        """Record request timing after a request"""
        self.request_count += 1
        self.last_request_time = time.time()
    
    def should_rotate_profile(self, max_requests: int = 50) -> bool:
        """Check if profile should be rotated after many requests"""
        return self.request_count >= max_requests
    
    def rotate_profile(self) -> None:
        """Generate a new fingerprint profile"""
        if self.session_id in _profile_cache:
            del _profile_cache[self.session_id]
        self.profile = generate_profile(self.session_id)
        self.request_count = 0


def clear_profile_cache() -> None:
    """Clear all cached profiles"""
    global _profile_cache
    _profile_cache.clear()


def get_stripe_headers(stripe_key: str, referer: str) -> Dict[str, str]:
    """
    Get headers specifically formatted for Stripe API requests.
    
    Args:
        stripe_key: Stripe publishable key
        referer: The merchant site URL
    
    Returns:
        Headers dict for Stripe API
    """
    profile = generate_profile()
    return {
        "User-Agent": profile.user_agent,
        "Accept": "application/json",
        "Accept-Language": profile.accept_language,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://js.stripe.com",
        "Referer": referer,
        "sec-ch-ua": profile._get_sec_ch_ua(),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{profile.platform}"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }


def get_braintree_headers(referer: str) -> Dict[str, str]:
    """
    Get headers specifically formatted for Braintree API requests.
    
    Args:
        referer: The merchant site URL
    
    Returns:
        Headers dict for Braintree API
    """
    profile = generate_profile()
    return {
        "User-Agent": profile.user_agent,
        "Accept": "*/*",
        "Accept-Language": profile.accept_language,
        "Content-Type": "application/json",
        "Origin": referer.rstrip('/'),
        "Referer": referer,
        "Braintree-Version": "2018-05-10",
        "sec-ch-ua": profile._get_sec_ch_ua(),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{profile.platform}"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }


def get_paypal_headers(referer: str) -> Dict[str, str]:
    """
    Get headers specifically formatted for PayPal API requests.
    
    Args:
        referer: The merchant site URL
    
    Returns:
        Headers dict for PayPal API
    """
    profile = generate_profile()
    return {
        "User-Agent": profile.user_agent,
        "Accept": "application/json",
        "Accept-Language": profile.accept_language,
        "Content-Type": "application/json",
        "Origin": "https://www.paypal.com",
        "Referer": referer,
        "x-requested-with": "XMLHttpRequest",
        "sec-ch-ua": profile._get_sec_ch_ua(),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{profile.platform}"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
