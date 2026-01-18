"""
CAPTCHA Solver Utility using NopeCHA API
Supports reCAPTCHA v2/v3 and hCaptcha
"""

import os
import requests
from typing import Optional, Dict, Any


NOPECHA_API_KEY = os.environ.get("NOPECHA_API_KEY", "")


def solve_recaptcha_v2(sitekey: str, url: str, timeout: int = 120) -> Optional[str]:
    """
    Solve reCAPTCHA v2 and return the token
    
    Args:
        sitekey: The reCAPTCHA sitekey from the page
        url: The URL where the captcha appears
        timeout: Max seconds to wait
    
    Returns:
        CAPTCHA token string or None if failed
    """
    if not NOPECHA_API_KEY:
        print("[CAPTCHA] No NopeCHA API key configured")
        return None
    
    try:
        from nopecha.api.requests import RequestsAPIClient
        
        client = RequestsAPIClient(NOPECHA_API_KEY)
        result = client.solve_recaptcha(sitekey, url)
        
        if result and result.get("data"):
            return result["data"]
        return None
        
    except ImportError:
        return _solve_via_api(sitekey, url, "recaptcha2", timeout)
    except Exception as e:
        print(f"[CAPTCHA] Error: {e}")
        return None


def solve_hcaptcha(sitekey: str, url: str, timeout: int = 120) -> Optional[str]:
    """
    Solve hCaptcha and return the token
    
    Args:
        sitekey: The hCaptcha sitekey from the page
        url: The URL where the captcha appears
        timeout: Max seconds to wait
    
    Returns:
        CAPTCHA token string or None if failed
    """
    if not NOPECHA_API_KEY:
        print("[CAPTCHA] No NopeCHA API key configured")
        return None
    
    try:
        from nopecha.api.requests import RequestsAPIClient
        
        client = RequestsAPIClient(NOPECHA_API_KEY)
        result = client.solve_hcaptcha(sitekey, url)
        
        if result and result.get("data"):
            return result["data"]
        return None
        
    except ImportError:
        return _solve_via_api(sitekey, url, "hcaptcha", timeout)
    except Exception as e:
        print(f"[CAPTCHA] Error: {e}")
        return None


def _solve_via_api(sitekey: str, url: str, captcha_type: str, timeout: int = 120) -> Optional[str]:
    """Fallback: Direct API call without library"""
    if not NOPECHA_API_KEY:
        return None
    
    try:
        headers = {
            'Content-Type': 'application/json',
        }
        
        data = {
            'key': NOPECHA_API_KEY,
            'type': captcha_type,
            'sitekey': sitekey,
            'url': url,
        }
        
        response = requests.post('https://api.nopecha.com/token', 
                                headers=headers, json=data, timeout=timeout)
        result = response.json()
        
        if result.get('data'):
            return result['data']
        
        return None
        
    except Exception as e:
        print(f"[CAPTCHA] API Error: {e}")
        return None


def get_balance() -> Dict[str, Any]:
    """Get NopeCHA account balance/status"""
    if not NOPECHA_API_KEY:
        return {"error": "No API key configured"}
    
    try:
        from nopecha.api.requests import RequestsAPIClient
        client = RequestsAPIClient(NOPECHA_API_KEY)
        return client.status()
    except ImportError:
        headers = {'Content-Type': 'application/json'}
        response = requests.post('https://api.nopecha.com/status',
                                headers=headers, json={'key': NOPECHA_API_KEY}, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    balance = get_balance()
    print(f"Balance: {balance}")
