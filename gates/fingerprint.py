"""
Fingerprint Module - Browser fingerprinting, mouse simulation, and human-like timing
Makes requests appear more like real browser traffic
"""

import random
import math
import time
import hashlib
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class BrowserFingerprint:
    """Complete browser fingerprint for a session"""
    user_agent: str
    platform: str
    screen_width: int
    screen_height: int
    color_depth: int
    timezone_offset: int
    language: str
    languages: List[str]
    hardware_concurrency: int
    device_memory: int
    canvas_hash: str
    webgl_vendor: str
    webgl_renderer: str
    touch_support: bool
    do_not_track: Optional[str]
    
    def to_headers(self) -> Dict[str, str]:
        """Convert fingerprint to HTTP headers"""
        mobile = "Android" in self.user_agent or "iPhone" in self.user_agent
        
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": ",".join(self.languages[:3]) + ";q=0.9",
            "Sec-CH-UA-Platform": f'"{self.platform}"',
            "Sec-CH-UA-Mobile": "?1" if mobile else "?0",
        }
        
        if self.do_not_track:
            headers["DNT"] = self.do_not_track
        
        return headers
    
    def get_client_hints(self) -> Dict[str, str]:
        """Get Sec-CH-* client hints headers"""
        return {
            "Sec-CH-UA-Platform": f'"{self.platform}"',
            "Sec-CH-UA-Platform-Version": f'"{random.randint(10, 14)}.0.0"',
            "Sec-CH-UA-Mobile": "?1" if "Android" in self.user_agent else "?0",
            "Sec-CH-UA-Full-Version-List": self._generate_full_version_list(),
        }
    
    def _generate_full_version_list(self) -> str:
        if "Chrome" in self.user_agent:
            ver = random.randint(120, 137)
            return f'"Chromium";v="{ver}", "Google Chrome";v="{ver}", "Not-A.Brand";v="99"'
        elif "Safari" in self.user_agent and "Chrome" not in self.user_agent:
            return '"Safari";v="17", "Not-A.Brand";v="99"'
        return '"Not-A.Brand";v="99"'


DESKTOP_PROFILES = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
        "platform": "Windows",
        "screens": [(1920, 1080), (2560, 1440), (1366, 768), (1536, 864)],
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER)",
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.6790.120 Safari/537.36",
        "platform": "Windows",
        "screens": [(1920, 1080), (2560, 1440), (3840, 2160)],
        "webgl_vendor": "Google Inc. (AMD)",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 580)",
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "platform": "macOS",
        "screens": [(2560, 1600), (1440, 900), (2880, 1800)],
        "webgl_vendor": "Apple Inc.",
        "webgl_renderer": "Apple M2 Pro",
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
        "platform": "macOS",
        "screens": [(1920, 1080), (2560, 1440)],
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderer": "ANGLE (Apple, Apple M1)",
    },
    {
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
        "platform": "Linux",
        "screens": [(1920, 1080), (2560, 1440)],
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderer": "ANGLE (Intel, Intel UHD Graphics 630)",
    },
]

MOBILE_PROFILES = [
    {
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
        "platform": "Android",
        "screens": [(1344, 2992), (1080, 2400)],
        "webgl_vendor": "Qualcomm",
        "webgl_renderer": "Adreno (TM) 750",
    },
    {
        "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
        "platform": "Android",
        "screens": [(1440, 3088), (1080, 2316)],
        "webgl_vendor": "Qualcomm",
        "webgl_renderer": "Adreno (TM) 740",
    },
    {
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "platform": "iOS",
        "screens": [(1179, 2556), (1284, 2778)],
        "webgl_vendor": "Apple Inc.",
        "webgl_renderer": "Apple GPU",
    },
]

LANGUAGES = [
    ["en-US", "en"],
    ["en-GB", "en"],
    ["en-CA", "en", "fr"],
    ["en-AU", "en"],
]

TIMEZONES = [-480, -420, -360, -300, -240, 0, 60, 120]


def generate_fingerprint(prefer_mobile: bool = False) -> BrowserFingerprint:
    """Generate a realistic browser fingerprint"""
    profiles = MOBILE_PROFILES if prefer_mobile else DESKTOP_PROFILES
    profile = random.choice(profiles)
    
    screen = random.choice(profile["screens"])
    langs = random.choice(LANGUAGES)
    
    canvas_seed = f"{profile['user_agent']}{random.randint(1, 10000)}"
    canvas_hash = hashlib.md5(canvas_seed.encode()).hexdigest()[:16]
    
    return BrowserFingerprint(
        user_agent=profile["user_agent"],
        platform=profile["platform"],
        screen_width=screen[0],
        screen_height=screen[1],
        color_depth=random.choice([24, 32]),
        timezone_offset=random.choice(TIMEZONES),
        language=langs[0],
        languages=langs,
        hardware_concurrency=random.choice([4, 8, 12, 16]),
        device_memory=random.choice([4, 8, 16]),
        canvas_hash=canvas_hash,
        webgl_vendor=profile["webgl_vendor"],
        webgl_renderer=profile["webgl_renderer"],
        touch_support=profile["platform"] in ["Android", "iOS"],
        do_not_track=random.choice([None, "1", None, None]),
    )


class MouseSimulator:
    """Simulates realistic mouse movement patterns"""
    
    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.current_x = screen_width // 2
        self.current_y = screen_height // 2
        self.movements: List[Dict] = []
    
    def move_to(self, target_x: int, target_y: int, steps: int = None) -> List[Dict]:
        """
        Generate realistic mouse movement to target position.
        Uses Bezier curves for natural-looking paths.
        """
        if steps is None:
            distance = math.sqrt((target_x - self.current_x)**2 + (target_y - self.current_y)**2)
            steps = max(5, int(distance / 50))
        
        movements = []
        
        cp1_x = self.current_x + random.randint(-50, 50) + (target_x - self.current_x) * 0.3
        cp1_y = self.current_y + random.randint(-50, 50) + (target_y - self.current_y) * 0.3
        cp2_x = target_x + random.randint(-30, 30) - (target_x - self.current_x) * 0.2
        cp2_y = target_y + random.randint(-30, 30) - (target_y - self.current_y) * 0.2
        
        for i in range(steps + 1):
            t = i / steps
            
            x = (1-t)**3 * self.current_x + 3*(1-t)**2*t * cp1_x + 3*(1-t)*t**2 * cp2_x + t**3 * target_x
            y = (1-t)**3 * self.current_y + 3*(1-t)**2*t * cp1_y + 3*(1-t)*t**2 * cp2_y + t**3 * target_y
            
            x += random.gauss(0, 1)
            y += random.gauss(0, 1)
            
            movements.append({
                "x": int(x),
                "y": int(y),
                "timestamp": int(time.time() * 1000) + i * random.randint(8, 25),
            })
        
        self.current_x = target_x
        self.current_y = target_y
        self.movements.extend(movements)
        
        return movements
    
    def click(self, x: int = None, y: int = None) -> Dict:
        """Generate a click event"""
        if x is None:
            x = self.current_x
        if y is None:
            y = self.current_y
        
        return {
            "type": "click",
            "x": x,
            "y": y,
            "button": 0,
            "timestamp": int(time.time() * 1000),
        }
    
    def scroll(self, delta_y: int = 100) -> Dict:
        """Generate a scroll event"""
        return {
            "type": "scroll",
            "x": self.current_x,
            "y": self.current_y,
            "deltaY": delta_y + random.randint(-20, 20),
            "timestamp": int(time.time() * 1000),
        }
    
    def get_interaction_data(self) -> Dict:
        """Get all interaction data for anti-bot systems"""
        return {
            "mouse_movements": len(self.movements),
            "last_position": {"x": self.current_x, "y": self.current_y},
            "interaction_count": len(self.movements),
        }


class GaussianTimer:
    """
    Human-like timing with Gaussian (normal) distribution.
    More realistic than uniform random delays.
    """
    
    @staticmethod
    def delay(mean: float = 1.0, std_dev: float = 0.3, min_val: float = 0.1, max_val: float = 5.0) -> float:
        """
        Generate a delay with Gaussian distribution.
        
        Args:
            mean: Average delay in seconds
            std_dev: Standard deviation (spread of values)
            min_val: Minimum allowed delay
            max_val: Maximum allowed delay
        
        Returns:
            Delay in seconds
        """
        delay = random.gauss(mean, std_dev)
        return max(min_val, min(max_val, delay))
    
    @staticmethod
    def sleep(mean: float = 1.0, std_dev: float = 0.3, min_val: float = 0.1, max_val: float = 5.0) -> None:
        """Sleep for a Gaussian-distributed duration"""
        time.sleep(GaussianTimer.delay(mean, std_dev, min_val, max_val))
    
    @staticmethod
    async def async_sleep(mean: float = 1.0, std_dev: float = 0.3, min_val: float = 0.1, max_val: float = 5.0) -> None:
        """Async sleep for a Gaussian-distributed duration"""
        import asyncio
        await asyncio.sleep(GaussianTimer.delay(mean, std_dev, min_val, max_val))
    
    @staticmethod
    def typing_delay() -> float:
        """Delay between keystrokes (50-150ms typical)"""
        return GaussianTimer.delay(mean=0.08, std_dev=0.03, min_val=0.03, max_val=0.2)
    
    @staticmethod
    def click_delay() -> float:
        """Delay before clicking (200-800ms typical)"""
        return GaussianTimer.delay(mean=0.4, std_dev=0.15, min_val=0.1, max_val=1.0)
    
    @staticmethod
    def page_load_delay() -> float:
        """Delay after page load before action (1-3s typical)"""
        return GaussianTimer.delay(mean=1.5, std_dev=0.5, min_val=0.5, max_val=4.0)
    
    @staticmethod
    def form_field_delay() -> float:
        """Delay between filling form fields"""
        return GaussianTimer.delay(mean=0.8, std_dev=0.3, min_val=0.2, max_val=2.0)


class SessionPersistence:
    """
    Manages persistent session data across multiple requests.
    Keeps cookies, fingerprints, and state for realistic multi-request sessions.
    """
    
    def __init__(self):
        self._sessions: Dict[str, Dict] = {}
    
    def get_or_create(self, domain: str) -> Dict:
        """Get existing session for domain or create new one"""
        if domain not in self._sessions:
            self._sessions[domain] = {
                "fingerprint": generate_fingerprint(),
                "cookies": {},
                "created_at": time.time(),
                "request_count": 0,
                "last_request": 0,
                "mouse": MouseSimulator(),
            }
        
        session = self._sessions[domain]
        session["request_count"] += 1
        session["last_request"] = time.time()
        
        return session
    
    def update_cookies(self, domain: str, cookies: Dict) -> None:
        """Update stored cookies for a domain"""
        if domain in self._sessions:
            self._sessions[domain]["cookies"].update(cookies)
    
    def get_cookies(self, domain: str) -> Dict:
        """Get stored cookies for a domain"""
        if domain in self._sessions:
            return self._sessions[domain].get("cookies", {})
        return {}
    
    def get_fingerprint(self, domain: str) -> Optional[BrowserFingerprint]:
        """Get consistent fingerprint for a domain"""
        session = self.get_or_create(domain)
        return session.get("fingerprint")
    
    def clear_old_sessions(self, max_age: float = 3600) -> int:
        """Clear sessions older than max_age seconds"""
        now = time.time()
        old = [d for d, s in self._sessions.items() if now - s["last_request"] > max_age]
        for domain in old:
            del self._sessions[domain]
        return len(old)
    
    def clear_all(self) -> int:
        """Clear all sessions"""
        count = len(self._sessions)
        self._sessions.clear()
        return count


_session_persistence = SessionPersistence()


def get_session_for_domain(domain: str) -> Dict:
    """Get or create a persistent session for a domain"""
    return _session_persistence.get_or_create(domain)


def get_fingerprint_headers(domain: str) -> Dict[str, str]:
    """Get consistent fingerprint headers for a domain"""
    fp = _session_persistence.get_fingerprint(domain)
    if fp:
        headers = fp.to_headers()
        headers.update(fp.get_client_hints())
        return headers
    return {}


def simulate_browsing_behavior(domain: str) -> Dict:
    """Simulate realistic browsing behavior for anti-bot detection"""
    session = get_session_for_domain(domain)
    mouse = session.get("mouse", MouseSimulator())
    fp = session.get("fingerprint")
    
    mouse.move_to(random.randint(100, 800), random.randint(100, 600))
    mouse.scroll(random.randint(100, 400))
    mouse.move_to(random.randint(400, 1200), random.randint(200, 800))
    
    return {
        "fingerprint": fp.canvas_hash if fp else None,
        "screen": f"{fp.screen_width}x{fp.screen_height}" if fp else None,
        "interactions": mouse.get_interaction_data(),
        "request_count": session.get("request_count", 1),
    }
